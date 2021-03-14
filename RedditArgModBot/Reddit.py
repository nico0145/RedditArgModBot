import praw
import os
from prawcore.exceptions import OAuthException, ResponseException

def get_reddit_object():
    try:
        app_key = os.getenv('app_key')
        app_secret = os.getenv('app_secret')
        username = os.getenv('USUARIO')
        password = os.getenv('password')
        reddit = praw.Reddit(client_id=app_key,
                        client_secret=app_secret,
                        username=username,
                        password=password,
                        user_agent=username)

        reddit.user.me()

        return {'status': 'success', 'data': reddit}

    except OAuthException as err:
        return {'status': 'error', 'data': 'Error: Unable to get API access, please make sure API credentials are correct and try again (check the username and password first)'}

    except ResponseException as err:
        return {'status': 'error', 'data': 'Error: ResponseException: ' + str(err)}

    except Exception as err:
        return {'status': 'error', 'data': 'Unexpected Error: ' + str(err)} 