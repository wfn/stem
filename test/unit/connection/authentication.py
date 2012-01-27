"""
Unit tests for the stem.connection.authenticate function.
"""

import unittest

import stem.connection
import stem.util.log as log
import test.mocking as mocking

def _get_all_auth_method_combinations():
  """
  Enumerates all types of authentication that a PROTOCOLINFO response may
  provide, returning a tuple with the AuthMethod enums.
  """
  
  for is_none in (False, True):
    for is_password in (False, True):
      for is_cookie in (False, True):
        for is_unknown in (False, True):
          auth_methods = []
          
          if is_none: auth_methods.append(stem.connection.AuthMethod.NONE)
          if is_password: auth_methods.append(stem.connection.AuthMethod.PASSWORD)
          if is_cookie: auth_methods.append(stem.connection.AuthMethod.COOKIE)
          if is_unknown: auth_methods.append(stem.connection.AuthMethod.UNKNOWN)
          
          yield tuple(auth_methods)

class TestAuthenticate(unittest.TestCase):
  """
  Under the covers the authentiate function really just translates a
  PROTOCOLINFO response into authenticate_* calls, then does prioritization
  on the exceptions if they all fail.
  
  This monkey patches the various functions authenticate relies on to exercise
  various error conditions, and make sure that the right exception is raised.
  """
  
  def setUp(self):
    mocking.mock(stem.connection.get_protocolinfo, mocking.no_op())
    mocking.mock(stem.connection.authenticate_none, mocking.no_op())
    mocking.mock(stem.connection.authenticate_password, mocking.no_op())
    mocking.mock(stem.connection.authenticate_cookie, mocking.no_op())
  
  def tearDown(self):
    mocking.revert_mocking()
  
  def test_with_get_protocolinfo(self):
    """
    Tests the authenticate() function when it needs to make a get_protocolinfo.
    """
    
    # tests where get_protocolinfo succeeds
    protocolinfo_response = mocking.get_protocolinfo_response(
      auth_methods = (stem.connection.AuthMethod.NONE, ),
    )
    
    mocking.mock(stem.connection.get_protocolinfo, mocking.return_value(protocolinfo_response))
    stem.connection.authenticate(None)
    
    # tests where get_protocolinfo raises an exception
    raised_exc = stem.socket.ProtocolError(None)
    mocking.mock(stem.connection.get_protocolinfo, mocking.raise_exception(raised_exc))
    self.assertRaises(stem.connection.IncorrectSocketType, stem.connection.authenticate, None)
    
    raised_exc = stem.socket.SocketError(None)
    mocking.mock(stem.connection.get_protocolinfo, mocking.raise_exception(raised_exc))
    self.assertRaises(stem.connection.AuthenticationFailure, stem.connection.authenticate, None)
  
  def test_all_use_cases(self):
    """
    Does basic validation that all valid use cases for the PROTOCOLINFO input
    and dependent functions result in either success or a AuthenticationFailed
    subclass being raised.
    """
    
    # mute the logger for this test since otherwise the output is overwhelming
    
    stem_logger = log.get_logger()
    stem_logger.setLevel(log.logging_level(None))
    
    # exceptions that the authentication functions are documented to raise
    all_auth_none_exc = (None,
      stem.connection.OpenAuthRejected(None))
    
    all_auth_password_exc = (None,
      stem.connection.PasswordAuthRejected(None),
      stem.connection.IncorrectPassword(None))
    
    all_auth_cookie_exc = (None,
      stem.connection.IncorrectCookieSize(None),
      stem.connection.UnreadableCookieFile(None),
      stem.connection.CookieAuthRejected(None),
      stem.connection.IncorrectCookieValue(None))
    
    # authentication functions might raise a controller error when
    # 'suppress_ctl_errors' is False, so including those
    
    control_exc = (
      stem.socket.ProtocolError(None),
      stem.socket.SocketError(None),
      stem.socket.SocketClosed(None))
    
    all_auth_none_exc += control_exc
    all_auth_password_exc += control_exc
    all_auth_cookie_exc += control_exc
    
    for protocolinfo_auth_methods in _get_all_auth_method_combinations():
      # protocolinfo input for the authenticate() call we'll be making
      protocolinfo_arg = mocking.get_protocolinfo_response(
        auth_methods = protocolinfo_auth_methods,
        cookie_path = "/tmp/blah",
      )
      
      for auth_none_exc in all_auth_none_exc:
        for auth_password_exc in all_auth_password_exc:
          for auth_cookie_exc in all_auth_cookie_exc:
            # determine if the authenticate() call will succeed and mock each
            # of the authenticate_* function to raise its given exception
            
            expect_success = False
            auth_mocks = {
              stem.connection.AuthMethod.NONE:
                (stem.connection.authenticate_none, auth_none_exc),
              stem.connection.AuthMethod.PASSWORD:
                (stem.connection.authenticate_password, auth_password_exc),
              stem.connection.AuthMethod.COOKIE:
                (stem.connection.authenticate_cookie, auth_cookie_exc),
            }
            
            for auth_method in auth_mocks:
              auth_function, raised_exc = auth_mocks[auth_method]
              
              if not raised_exc:
                # Mocking this authentication method so it will succeed. If
                # it's among the protocolinfo methods then expect success.
                
                mocking.mock(auth_function, mocking.no_op())
                expect_success |= auth_method in protocolinfo_auth_methods
              else:
                mocking.mock(auth_function, mocking.raise_exception(raised_exc))
            
            if expect_success:
              stem.connection.authenticate(None, "blah", protocolinfo_arg)
            else:
              self.assertRaises(stem.connection.AuthenticationFailure, stem.connection.authenticate, None, "blah", protocolinfo_arg)
    
    # revert logging back to normal
    stem_logger.setLevel(log.logging_level(log.TRACE))

