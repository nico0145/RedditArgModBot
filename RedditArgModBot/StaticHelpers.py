import os
import asyncpraw
import json
import logging
from datetime import datetime
from prawcore.exceptions import OAuthException, ResponseException
from types import SimpleNamespace
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
async def async_get_reddit_object():
    try:
        app_key = os.getenv('app_key')
        app_secret = os.getenv('app_secret')
        username = os.getenv('USUARIO')
        password = os.getenv('password')
        reddit = asyncpraw.Reddit(client_id=app_key,
                        client_secret=app_secret,
                        username=username,
                        password=password,
                        user_agent=username)

        await reddit.user.me()

        return {'status': 'success', 'data': reddit}

    except OAuthException as err:
        return {'status': 'error', 'data': 'Error: Unable to get API access, please make sure API credentials are correct and try again (check the username and password first)'}

    except ResponseException as err:
        return {'status': 'error', 'data': 'Error: ResponseException: ' + str(err)}

    except Exception as err:
        return {'status': 'error', 'data': 'Unexpected Error: ' + str(err)} 
def GetSchedPostsFromWiki(wiki):
    return json.loads(wiki.content_md.replace("\t","").replace("\n",""),object_hook=lambda d: SimpleNamespace(**d))
def Log(Text,color,level):
    print(f"{color}{Text}{bcolors.ENDC}\n------")
    logging.log(level,Text)
def ReplaceStringFormat(sIn):
    sIn = sIn.replace('[FechaCorta]', datetime.utcnow().strftime('%d/%m'))
    return sIn
async def PostSchedPost(DB, reddit, subreddit, schedPost):
    Log(f"Posting ID: {schedPost.Id} - Next Date: {schedPost.nextTime}",bcolors.OKCYAN,logging.INFO)
    flair = ""
    async for template in subreddit.flair.link_templates:
        if schedPost.Flair.lower() in template['text'].lower():
            flair = template['id']
    if len(flair)>0:
        post = await subreddit.submit(title = ReplaceStringFormat(schedPost.Title), selftext = ReplaceStringFormat(schedPost.Body), flair_id = flair, send_replies = False, nsfw = False, spoiler = False)
        await post.load()
        await post.mod.suggested_sort(schedPost.Sort)
        if schedPost.TimeLenght > 0:
            await post.mod.sticky(bottom=schedPost.StickyPos == 2)
            await VerifyUnstickyReplace(reddit)
        row = (schedPost.Id,datetime.utcfromtimestamp(post.created_utc).strftime('%Y-%m-%d %H:%M:%S.%f'),post.id, schedPost.TimeLenght > 0)
        await SaveSchedPost(DB, row)
        return True
    else:
        Log(f"Error while posting scheduled post: flair {schedPost.Flair} not found",bcolors.WARNING,logging.WARNING)
        return False
async def SaveSchedPost(DB, row):
    DB.WriteDB("""INSERT INTO ScheduledPosts (RedditID,PostedDate, PostID, IsStickied) VALUES (?,?,?,?);""", row)