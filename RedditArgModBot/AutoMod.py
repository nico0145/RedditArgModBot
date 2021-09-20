import os
import sqlite3 as sl
from dotenv import load_dotenv
from Reddit import get_reddit_object
import asyncio
import threading
import time
from datetime import datetime
import logging
import asyncpraw
import opengraph_py3
import urllib.request
from bs4 import BeautifulSoup

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


def async_get_reddit_object():
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

        reddit.user.me()

        return {'status': 'success', 'data': reddit}

    except OAuthException as err:
        return {'status': 'error', 'data': 'Error: Unable to get API access, please make sure API credentials are correct and try again (check the username and password first)'}

    except ResponseException as err:
        return {'status': 'error', 'data': 'Error: ResponseException: ' + str(err)}

    except Exception as err:
        return {'status': 'error', 'data': 'Unexpected Error: ' + str(err)} 
def Log(Text,color,level):
    print(f"{color}{Text}{bcolors.ENDC}\n------")
    logging.log(level,Text)

def main():
    if os.name == 'nt': # Only if we are running on Windows
        from ctypes import windll
        k = windll.kernel32
        k.SetConsoleMode(k.GetStdHandle(-11), 7)
    load_dotenv()
    logging.basicConfig(filename=os.getenv('AutomodLog'), encoding='utf-8', format='[%(asctime)s] %(message)s',  level=logging.INFO)
    con = sl.connect(os.getenv('DB'))
    rres = async_get_reddit_object()
    if rres['status'] == 'success':
        reddit = rres['data']
        Start(reddit,con)
    else:
        Log(rres['data'],bcolors.WARNING,logging.WARNING)


def Start(reddit,con):
    Log("Automod Started...",bcolors.OKCYAN,logging.INFO)
    asyncio.Task(AutoModComments(reddit,con))
    asyncio.Task(AutoModPosts(reddit,con))
    asyncio.Task(ModLog(reddit,con))
    loop = asyncio.get_event_loop()
    loop.run_forever()

def ReApproveUser(con,User):
    con.execute(f"insert into PassFilterUser(User,Date) values('{User}',DATETIME())")
    con.commit()
def GetSetting(con,setting):
    cur = con.cursor()
    cur.execute(f"SELECT [Value] FROM Settings where [Key] = '{setting}'")
    rows = cur.fetchall()
    return rows[0][0]
def GetAVGWeight(con):
    ActionExpires = GetSetting(con,"warnexpires")
    cur = con.cursor()
    cur.execute(f"select avg(at.Weight) from Actions A JOIN ActionType AT on AT.id = A.ActionType where [ActionType] in (select id from ActionType where Weight < (select min([from]) from Policies where action = 2 and BanDays = -1) and Weight > 0) and [Date] > date(DATE(), '-{ActionExpires} day')")
    rows = cur.fetchall()
    return rows[0][0]
def GetLastActionDate(con,User):
    cur = con.cursor()
    cur.execute(f"select max(Date) from Actions where User = '{User}'")
    rows = cur.fetchall()
    return rows[0][0]
def IsTroubleUser(con,User):
    ActionExpires = GetSetting(con,"warnexpires")
    #Avg = GetAVGWeight(con)
    BaseThreshold = GetSetting(con,"PuntosUsuarioProblematico")
    cur = con.cursor()
    cur.execute(f"select case when max(PFU.Date) > max(A.Date) then 'Pass' when sum(at.Weight) is null then 'Pass' when sum(at.Weight) < {BaseThreshold} THEN 'Pass' ELSE 'Block' end as 'Filter' from Actions A JOIN ActionType AT on AT.id = A.ActionType LEFT JOIN PassFilterUser PFU on PFU.User = A.User where A.User = '{User}' and [A].[Date] > date(DATE(), '-{ActionExpires} day')")
    rows = cur.fetchall()
    return rows[0][0]

async def AutoModComments(reddit,con):
    subreddit = await reddit.subreddit(GetSetting(con,"subreddit"))
    async for submission in subreddit.stream.comments(skip_existing=True):
        await AnalyzeSubmitter(con, subreddit, submission,"comment")
async def AutoModPosts(reddit,con):
    subreddit = await reddit.subreddit(GetSetting(con,"subreddit"))
    async for submission in subreddit.stream.submissions(skip_existing=True):
        await AnalyzeSubmitter(con, subreddit, submission,"post")
async def ModLog(reddit,con):
    subreddit = await reddit.subreddit(GetSetting(con,"subreddit"))
    async for log in subreddit.mod.stream.modqueue():
        if len(log.user_reports) == 0  and log.mod_note =='cuenta nueva':
            redditor = await reddit.redditor(log.author.name, fetch=True)
            created = redditor.created_utc
            await AnalyzeNewAccountAction(subreddit, log.author, log, created, con)

async def AnalyzeNewAccountAction(subreddit, author, log, created, con):
    Log(f"Veryfing new account submission for User: {author.name}",bcolors.OKCYAN,logging.DEBUG)
    PostsLeft = await AllowNewAccount(subreddit, author, created, con)
    if PostsLeft == 0:
        Log(f"User: {author.name} Passed the new account filter, approving submission in modqueue:\n{log.permalink}",bcolors.OKCYAN,logging.INFO)
        await log.mod.approve()
    else:
        Log(f"User: {author.name} didn't pass the new account filter, {PostsLeft} posts left",bcolors.OKCYAN,logging.DEBUG)

async def AllowNewAccount(subreddit, author, end_date,con):
    lastActionDate = GetLastActionDate(con, author.name)
    EntryLimit = int(GetSetting(con,"PostsFiltroAutomod"))
    if lastActionDate is not None:
        lastActionDate = time.mktime(datetime.strptime(lastActionDate, '%Y-%m-%d %H:%M:%S.%f').timetuple())
        if lastActionDate > end_date: #Si tiene cualquier tipo de medidas reducimos la fecha a la fecha de la ultima medida para ahorrar tiempo de busqueda
            end_date = lastActionDate
    posts = []
    async for submission in author.submissions.new():
        if submission.created_utc < end_date:
            break
        if submission.subreddit.display_name.lower() == subreddit.display_name.lower():
            posts.append({'removed': submission.removed, 'date': submission.created_utc})
    async for comment in author.comments.new():
        if comment.created_utc < end_date:
            break
        if comment.subreddit.display_name.lower() == subreddit.display_name.lower():
            posts.append({'removed': comment.removed, 'date': comment.created_utc})
    sortedposts = sorted(posts, key=lambda x: x['date'], reverse=True)
    for post in sortedposts:
        if post['removed'] == False:
            EntryLimit-=1
            if EntryLimit == 0:
                break
        else:
            break
    return EntryLimit

async def AnalyzeSubmitter(con, subreddit, submission, type):
    Log(f"Checking new submission by User: {submission.author.name}",bcolors.OKBLUE,logging.DEBUG)
    if IsTroubleUser(con, submission.author.name) == "Block":
        asyncio.create_task(HandleTroubleUser(con, subreddit, submission))
    else:
        Log(f"User {submission.author.name} verified.",bcolors.OKBLUE,logging.DEBUG)
    if type == "post":
        asyncio.create_task(OneHourBetweenPosts(subreddit, submission))
        asyncio.create_task(URLTitle(subreddit, submission))

async def URLTitle(subreddit, submission):
    if submission.is_reddit_media_domain == False and submission.is_self == False:
        if GetWebsiteTitle(submission.url).lower().strip(' ') != submission.title.lower().strip(' '):
            await submission.report(f"Revisar editorializacion en el titulo")
            Log(f"Post title: \'{submission.title}\' doesn't match website's: \'{website['title']}\' User: {submission.author.name} the post was reported to the modqueue", bcolors.WARNING,logging.INFO)
        else:
            Log(f"Post title for user {submission.author.name} match the website's",bcolors.WARNING,logging.DEBUG)
def GetWebsiteTitle(URL):
    with urllib.request.urlopen(URL) as response:
        webpage = response.read()
        soup = BeautifulSoup(webpage, "lxml")
        title = soup.find("meta", property="og:title")
        if title is None:
            title = soup.title.string
    return title["content"] if title else ""

async def OneHourBetweenPosts(subreddit, submission):
    end_date = submission.created_utc - 1*60*60
    async for oldsubmission in submission.author.submissions.new():
        if oldsubmission.created_utc < end_date:
            break
        if oldsubmission.subreddit.display_name.lower() == subreddit.display_name.lower() and oldsubmission != submission:
            TimeLeft = time.strftime("%M:%S", time.gmtime(end_date - oldsubmission.created_utc))
            Log(f"Less than an hour ({TimeLeft}) between posts for User {submission.author.name} the post was reported to the modqueue",bcolors.WARNING,logging.INFO)
            await submission.report(f"Dejar pasar una hora entre posts (Tiempo entre posteos: {TimeLeft})")

async def HandleTroubleUser(con, subreddit, submission):
    Log(f"User {submission.author.name} is flagged as a troublesome user, checking last mod actions...",bcolors.WARNING,logging.DEBUG)
    PostsLeft = await AllowNewAccount(subreddit, submission.author, 0,con)
    if PostsLeft == 0:
        ReApproveUser(con, submission.author.name)
        Log(f"User {submission.author.name} re-approved",bcolors.OKGREEN,logging.INFO)
    else:
        Log(f"Troublesome User {submission.author.name} has been reported to the modqueue, {PostsLeft} posts left",bcolors.WARNING,logging.INFO)
        await submission.report(f"Usuario Problematico por otros {PostsLeft} posteos")

if __name__ == "__main__":
    main()