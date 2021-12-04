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
import urllib.request
import requests
from bs4 import BeautifulSoup
import sys
import tweepy
from dateutil.relativedelta import *
import ssl
import re
from DBHandle import *
from StaticHelpers import *

def ReApproveUser(User):
    DB.WriteDB(f"insert into PassFilterUser(User,Date) values('{User}',DATETIME())")
def GetAVGWeight():
    ActionExpires = DB.GetSetting("warnexpires")
    return DB.GetDBValue(f"select avg(at.Weight) from Actions A JOIN ActionType AT on AT.id = A.ActionType where [ActionType] in (select id from ActionType where Weight < (select min([from]) from Policies where action = 2 and BanDays = -1) and Weight > 0) and [Date] > date(DATE(), '-{ActionExpires} day')")
def GetLastActionDate(User):
    return DB.GetDBValue(f"select max(Date) from Actions where User = '{User}'")
def IsTroubleUser(User):
    ActionExpires = DB.GetSetting("warnexpires")
    #Avg = GetAVGWeight()
    BaseThreshold = DB.GetSetting("PuntosUsuarioProblematico")
    return DB.GetDBValue(f"select case when max(PFU.Date) > max(A.Date) then 'Pass' when sum(at.Weight) is null then 'Pass' when sum(at.Weight) < {BaseThreshold} THEN 'Pass' ELSE 'Block' end as 'Filter' from Actions A JOIN ActionType AT on AT.id = A.ActionType LEFT JOIN PassFilterUser PFU on PFU.User = A.User where A.User = '{User}' and [A].[Date] > date(DATE(), '-{ActionExpires} day')")
load_dotenv()
DB = DBHandle(os.getenv('DB'))
sSubReddit = DB.GetSetting("subreddit")
async def main():
    if os.name == 'nt': # Only if we are running on Windows
        from ctypes import windll
        k = windll.kernel32
        k.SetConsoleMode(k.GetStdHandle(-11), 7)
    logging.basicConfig(filename=os.getenv('AutomodLog'), encoding='utf-8', format='[%(asctime)s] %(message)s',  level=logging.INFO)
    rres = await async_get_reddit_object()
    if rres['status'] == 'success':
        reddit = rres['data']
        reddit.validate_on_submit = True
        await Start(reddit)
    else:
        Log(rres['data'],bcolors.WARNING,logging.WARNING)


async def Start(reddit):
    Log("Automod Started...",bcolors.OKCYAN,logging.INFO)
    ssl._create_default_https_context = ssl._create_unverified_context
    #asyncio.Task(DebugCases(reddit))
    asyncio.Task(ModLog(reddit))
    asyncio.Task(AutoModComments(reddit))
    asyncio.Task(AutoModPosts(reddit))
    asyncio.Task(ModQueue(reddit))
    asyncio.Task(Scheduler(reddit))

async def DebugCases(reddit):
    subreddit = await reddit.subreddit(sSubReddit)
    #subreddit = await reddit.subreddit("GenteSexyRadio") #Para debug
    #submission2 = await reddit.submission("qq38sl")
    comment = asyncpraw.models.Comment(reddit,url = 'http://www.reddit.com/r/argentina/comments/qpr5pb/_/hjwsmm7')#await reddit.get_submission('http://www.reddit.com/r/argentina/comments/qpr5pb/_/hjwsmm7').comments[0]
    await comment.load()
    #await AnalyzeSubmitter(subreddit, submission2,"post")
    #await URLTitle(subreddit, submission2) #para debug
    #await CheckSpamPost(subreddit, submission2)
    await CheckSpamComment(subreddit, comment)
async def Scheduler(reddit):
    subreddit = await reddit.subreddit(sSubReddit)
    wikiupdatesecscount = 0
    while True:
        try:
            wikiobj = await GetWikiObj(subreddit)
            revisionDate = wikiobj[0]
            schedPosts = wikiobj[1]
            while True:
                stickied = filter(lambda x: x.IsStickied == True, schedPosts.SchedPosts)
                for schedPost in stickied:
                    #check if they need to be unstickied first
                    await CheckUnsticky(schedPost, reddit)
                for schedPost in schedPosts.SchedPosts:
                    if schedPost.nextTime > schedPost.lastPosted and schedPost.nextTime < datetime.utcnow():
                        if await PostSchedPost(DB, reddit, subreddit, schedPost):
                            schedPost.nextTime = GetNextScheduledPostTime(schedPost)
                            GetLastPostedID(schedPost)
                await asyncio.sleep(1)
                wikiupdatesecscount +=1
                if wikiupdatesecscount > 45:
                    wikiupdatesecscount = 0
                    wikiobj = await GetWikiObj(subreddit)
                    if wikiobj[0] > revisionDate:
                        schedPosts = wikiobj[1]
        except:
            Log(f"Error while doing scheduler: {sys.exc_info()[1]}",bcolors.WARNING,logging.WARNING)
async def PostSchedPost(reddit, subreddit, schedPost):
    Log(f"Posting ID: {schedPost.Id} - Next Date: {schedPost.nextTime}",bcolors.OKCYAN,logging.INFO)
    flair = ""
    async for template in subreddit.flair.link_templates:
        if schedPost.Flair.lower() in template['text'].lower():
            flair = template['id']
    if len(flair)>0:
        post = await subreddit.submit(title = ReplaceStringFormat(schedPost.Title), selftext = ReplaceStringFormat(schedPost.Body), flair_id = flair, send_replies = False, nsfw = False, spoiler = False)
        if schedPost.TimeLenght > 0:
            await post.load()
            await post.mod.suggested_sort(schedPost.Sort)
            await post.mod.sticky(bottom=schedPost.StickyPos == 2)
            await VerifyUnstickyReplace(reddit)
        row = (schedPost.Id,datetime.utcfromtimestamp(post.created_utc).strftime('%Y-%m-%d %H:%M:%S.%f'),post.id, schedPost.TimeLenght > 0)
        await SaveSchedPost(row)
        return True
    else:
        Log(f"Error while posting scheduled post: flair {schedPost.Flair} not found",bcolors.WARNING,logging.WARNING)
        return False
async def VerifyUnstickyReplace(reddit):
    StickiedPosts = DB.ExecuteDB("select PostID from ScheduledPosts where IsStickied = 1")
    for postID in StickiedPosts:
        Post = await reddit.submission(postID[0])
        if Post.stickied == False:
            DB.WriteDB(f"Update ScheduledPosts set IsStickied = false where PostID = '{postID[0]}'")
            Log(f"Post ID: {postID[0]} - Sticky was replaced.",bcolors.OKCYAN,logging.INFO)
async def SaveSchedPost(row):
    DB.WriteDB("""INSERT INTO ScheduledPosts (RedditID,PostedDate, PostID, IsStickied) VALUES (?,?,?,?);""", row)
def GetLastPostedID(schedPost):
    schedPost.CurrDBId = DB.GetDBValue(f"SELECT max(Id) FROM ScheduledPosts where [RedditID] = {schedPost.Id}")
    if schedPost.CurrDBId == None:
        schedPost.lastPosted = datetime.min
        schedPost.PostID = ""
        schedPost.IsStickied = False
    else:
        DBRow = DB.ExecuteDB(f"SELECT [PostedDate], [IsStickied], PostID FROM ScheduledPosts where Id = {schedPost.CurrDBId}")[0]
        schedPost.lastPosted = datetime.strptime(DBRow[0], '%Y-%m-%d %H:%M:%S.%f')
        schedPost.IsStickied = DBRow[1]
        schedPost.PostID = DBRow[2]
async def CheckUnsticky(schedPost, reddit):
    if len(schedPost.PostID) > 0:
        if schedPost.TimeLenght > 0:
            mlastPosted = schedPost.lastPosted + relativedelta(seconds=+schedPost.TimeLenght)
        if mlastPosted < datetime.utcnow():
            post = await reddit.submission(schedPost.PostID)
            await post.mod.sticky(state = False)
            DB.WriteDB(f"Update ScheduledPosts set IsStickied = false where Id = {schedPost.CurrDBId}")
            schedPost.IsStickied = False
            Log(f"Post ID: {schedPost.PostID} - unstickied",bcolors.OKCYAN,logging.INFO)
        #unsticky
async def GetWikiObj(subreddit):
    wiki = await subreddit.wiki.get_page("scheduledposts")
    schedPosts = GetSchedPostsFromWiki(wiki)
    for schedPost in schedPosts.SchedPosts:
        schedPost.nextTime = GetNextScheduledPostTime(schedPost)
        GetLastPostedID(schedPost)
    return (wiki.revision_date, schedPosts)

#gets the next datetime you post
#if the date is in the past then you can't post anymore unless the date is posterior to the last posted date in the DB
def GetNextScheduledPostTime(SchedPost):
    nextDate = datetime.strptime(SchedPost.StartDate, '%Y-%m-%d %H:%M:%S.%f')
    iterations = 1
    repeatUnit = SchedPost.RepeatUnit.lower()
    prevDate = nextDate
    while ContinueSchedEval(nextDate, iterations, SchedPost):
        prevDate = nextDate
        if repeatUnit == "custom":
            weekdays = str(SchedPost.RepeatValue).zfill(7)
            foundNext = False
            while not foundNext:
                nextDate = nextDate + relativedelta(days=+1)
                foundNext = weekdays[nextDate.weekday()] == "1"
        elif repeatUnit == "minute":
            nextDate = nextDate + relativedelta(minutes=+SchedPost.RepeatValue)
        elif repeatUnit == "hour":
            nextDate = nextDate + relativedelta(hours=+SchedPost.RepeatValue)
        elif repeatUnit == "day":
            nextDate = nextDate + relativedelta(days=+SchedPost.RepeatValue)
        elif repeatUnit == "week":
            nextDate = nextDate + relativedelta(weeks=+SchedPost.RepeatValue)
        elif repeatUnit == "month":
            nextDate = nextDate + relativedelta(months=+SchedPost.RepeatValue)
        elif repeatUnit == "year":
            nextDate = nextDate + relativedelta(years=+SchedPost.RepeatValue)
        iterations += 1
    if SchedPost.EndsUnit.lower() == "date":
        cutoff = datetime.strptime(SchedPost.EndsValue, '%Y-%m-%d %H:%M:%S.%f')
        if cutoff < nextDate:
            nextDate = prevDate
    return nextDate
def passEndDate(nextDate,SchedPost):
    cutoff = datetime.strptime(SchedPost.EndsValue, '%Y-%m-%d %H:%M:%S.%f')
    if cutoff > datetime.utcnow():
        cutoff = datetime.utcnow()
    return nextDate < cutoff
def ContinueSchedEval(nextDate, iterations,SchedPost):
    endUnit = SchedPost.EndsUnit.lower()
    if endUnit == "date":
        return passEndDate(nextDate,SchedPost)
    if endUnit == "occurrences":
        if iterations < SchedPost.EndsValue:
            return nextDate < datetime.utcnow()
        return False
    #else, Never
    return nextDate < datetime.utcnow()
async def AutoModComments(reddit):
    subreddit = await reddit.subreddit(sSubReddit)
    while True:
        try:
            async for submission in subreddit.stream.comments(skip_existing=True):
                await AnalyzeSubmitter(subreddit, submission,"comment")
        except:
            Log(f"Error while streaming comments: {sys.exc_info()[1]}",bcolors.WARNING,logging.WARNING)
async def AutoModPosts(reddit):
    subreddit = await reddit.subreddit(sSubReddit)
    while True:
        try:
            async for submission in subreddit.stream.submissions(skip_existing=True):
                await AnalyzeSubmitter(subreddit, submission,"post")
        except:
            Log(f"Error while streaming comments: {sys.exc_info()[1]}",bcolors.WARNING,logging.WARNING)
async def ModQueue(reddit):
    subreddit = await reddit.subreddit(sSubReddit)
    while True:
        try:
            async for log in subreddit.mod.stream.modqueue():
                if len(log.user_reports) == 0  and log.mod_note =='cuenta nueva' and log.author is not None:
                    redditor = await reddit.redditor(log.author.name, fetch=True)
                    if hasattr(redditor, 'is_suspended') and redditor.is_suspended == True:
                        Log(f"La cuenta del usuario {redditor.stream.redditor.name} fue suspendida por Reddit",bcolors.WARNING,logging.INFO)
                    else:
                        created = redditor.created_utc
                        await AnalyzeNewAccountAction(subreddit, log.author, log, created)
        except:
            Log(f"Error while streaming ModQueue: {sys.exc_info()[1]}",bcolors.WARNING,logging.WARNING)
async def ModLog(reddit):
    subreddit = await reddit.subreddit(sSubReddit)
    while True:
        maxDatestr = DB.GetDBValue("select max(date) as 'Date' from ModLog")
        MaxDate = 0
        if maxDatestr is not None:
            MaxDate = time.mktime(datetime.strptime(maxDatestr, '%Y-%m-%d %H:%M:%S.%f').timetuple())
        try:
            async for log in subreddit.mod.stream.log():
                if(log.created_utc > MaxDate):
                    row = (log.action,datetime.fromtimestamp(log.created_utc).strftime('%Y-%m-%d %H:%M:%S.%f'),log.description,log.mod.name,log.target_author,log.target_permalink )
                    await SaveLog(row)
        except:
            Log(f"Error while streaming ModLog: {sys.exc_info()[1]}",bcolors.WARNING,logging.WARNING)

async def SaveLog(row):
    DB.WriteDB("""INSERT INTO ModLog (Action,Date, Description, ModName, Author, Permalink) VALUES (?,?,?,?,?,?);""", row)
async def AnalyzeNewAccountAction(subreddit, author, log, created):
    Log(f"Veryfing new account submission for User: {author.name}",bcolors.OKCYAN,logging.DEBUG)
    PostsLeft = await AllowNewAccount(subreddit, author, created)
    if PostsLeft == 0:
        Log(f"User: {author.name} Passed the new account filter, approving submission in modqueue:\n{log.permalink}",bcolors.OKCYAN,logging.INFO)
        await log.mod.approve()
    else:
        Log(f"User: {author.name} didn't pass the new account filter, {PostsLeft} posts left",bcolors.OKCYAN,logging.DEBUG)

async def AllowNewAccount(subreddit, author, end_date):
    async for contributor in subreddit.contributor():
        if author.name == contributor.name: #si el usuario esta en la lista de usuarios aprobados entonces no pasa por el filtro de cuenta nueva
            return 0
    lastActionDate = GetLastActionDate(author.name)
    EntryLimit = int(DB.GetSetting("PostsFiltroAutomod"))
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

async def AnalyzeSubmitter(subreddit, submission, type):
    if submission.author is None:
        await submission.report(f"Usuario eliminado.")
        Log(f"No author found for submission: \'{submission.title}\' URL: {submission.permalink} the post was reported to the modqueue", bcolors.WARNING,logging.INFO)
    else:
        Log(f"Checking new submission by User: {submission.author.name}",bcolors.OKBLUE,logging.DEBUG)
        if IsTroubleUser(submission.author.name) == "Block":
            asyncio.create_task(HandleTroubleUser(subreddit, submission))
        else:
            Log(f"User {submission.author.name} verified.",bcolors.OKBLUE,logging.DEBUG)
        if type == "post":
            asyncio.create_task(OneHourBetweenPosts(subreddit, submission))
            if submission.is_reddit_media_domain == False and submission.is_self == False:
                #asyncio.create_task(CheckSpamPost(subreddit, submission))
                if "twitter.com/" in submission.url:
                    asyncio.create_task(CheckTwitter(subreddit, submission))
                else:
                    checkFlairs=['economía','policiales', 'noticia', 'coronavirus', 'deportes']
                    if any(flairtext in submission.link_flair_text.lower() for flairtext in checkFlairs):
                        asyncio.create_task(URLTitle(subreddit, submission))
        #else:
            #asyncio.create_task(CheckSpamComment(subreddit, submission))
async def CheckSpamPost(subreddit, Origsubmission):
    try:
        counter = 0
        Log(f"Checking spam post for permalink {Origsubmission.permalink}", bcolors.WARNING,logging.DEBUG)
        async for submission in Origsubmission.author.submissions.new(limit=3):
            if submission.is_reddit_media_domain == False and submission.is_self == False and submission.url == Origsubmission.url:
                counter +=1
        if counter == 3:
            await Origsubmission.report(f"Posible Spam Bot.")
            Log(f"User: {Origsubmission.author.name} posted the same link at least 3 times. The post was reported to the modqueue", bcolors.WARNING,logging.INFO)
    except Exception as err:
        Log(f"Error on CheckSpamPost: {str(err)}", bcolors.WARNING,logging.ERROR)
async def CheckSpamComment(subreddit, Origsubmission):
    try:
        regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
        url = re.findall(regex,Origsubmission.body)
        Log(f"Checking spam comment for permalink {Origsubmission.permalink}", bcolors.WARNING,logging.DEBUG)
        if len(url) > 0 and len(url[0]) > 0:
            counter = 0
            await Origsubmission.author.load()
            async for submission in Origsubmission.author.comments.new(limit=3):
                if url[0][0] in submission.body:
                    counter +=1
            if counter == 3:
                await Origsubmission.report(f"Posible Spam Bot.")
                Log(f"User: {Origsubmission.author.name} posted the same link at least 3 times. The post was reported to the modqueue", bcolors.WARNING,logging.INFO)
    except Exception as err:
        Log(f"Error on CheckSpamComment: {str(err)}", bcolors.WARNING,logging.ERROR)
async def CheckTwitter(subreddit, submission):
    auth = tweepy.AppAuthHandler(os.getenv('tw_consumer_key'), os.getenv('tw_consumer_secret'))
    api = tweepy.API(auth)
    sIn = submission.url
    sIn = sIn.lstrip('http')
    sIn = sIn.lstrip('s')
    sIn = sIn.lstrip('://')
    sIn = sIn.lstrip('www.')
    chunks = sIn.split('/')
    if "/status" in sIn:
        status = api.get_status(chunks[-1])
        user = status.user
    else:
        user = api.get_user(chunks[1])
    if user.verified == False:
        await submission.report(f"Tweet de cuenta no verificada.")
        Log(f"User: {submission.author.name} posted an unverified tweet. The post was reported to the modqueue", bcolors.WARNING,logging.INFO)
    else:
        Log(f"User: {submission.author.name} posted a verified twitt.", bcolors.WARNING,logging.DEBUG)
def NormalizeTitle(sIn):
    return sIn.lower().strip(' ').replace('"','\'')
async def URLTitle(subreddit, submission):
    try:
        if submission.is_reddit_media_domain == False and submission.is_self == False:
            url = submission.url
            if hasattr(submission, "crosspost_parent"):
                url = f"https://www.reddit.com{submission.url}"
            webtitle = await GetWebsiteTitle(url)
            if len(webtitle) > 0:
                if NormalizeTitle(webtitle) != NormalizeTitle(submission.title):
                    await submission.report(f"Revisar editorializacion en el titulo.")
                    Log(f"Post title: \'{submission.title}\' doesn't match website's: \'{webtitle}\' User: {submission.author.name} the post was reported to the modqueue", bcolors.WARNING,logging.INFO)
                else:
                    Log(f"Post title for user {submission.author.name} match the website's",bcolors.WARNING,logging.DEBUG)
    except: 
        Log(f"Error while checking post title: {sys.exc_info()[1]}\nUser:{submission.author.name} - Permalink: {submission.permalink}",bcolors.WARNING,logging.WARNING)
async def GetWebsiteTitle(URL):
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36'
    headers = {'User-Agent':user_agent}#requests.utils.default_headers()
    req = urllib.request.Request(URL,None, headers=headers)
    with urllib.request.urlopen(req) as response:
        webpage = response.read()
        soup = BeautifulSoup(webpage, "lxml")
        title = soup.find("meta", property="og:title")
        stitle = None
        if title is None:
            if soup.title is not None:
                stitle = soup.title.string
        else:
            stitle = title["content"]
    return stitle if stitle else ""

async def OneHourBetweenPosts(subreddit, submission):
    try:
        end_date = submission.created_utc - 1*60*60
        async for oldsubmission in submission.author.submissions.new():
            if oldsubmission.created_utc < end_date:
                break
            if oldsubmission.subreddit.display_name.lower() == subreddit.display_name.lower() and oldsubmission != submission and not oldsubmission.removed:
                TimeLeft = time.strftime("%M:%S", time.gmtime(end_date - oldsubmission.created_utc))
                Log(f"Less than an hour ({TimeLeft}) between posts for User {submission.author.name} the post was reported to the modqueue",bcolors.WARNING,logging.INFO)
                await submission.report(f"Dejar pasar una hora entre posts (Tiempo entre posteos: {TimeLeft})")
    except Exception as err:
        Log(f"Error on OneHourBetweenPosts: {str(err)}", bcolors.WARNING,logging.ERROR)
async def HandleTroubleUser(subreddit, submission):
    Log(f"User {submission.author.name} is flagged as a troublesome user, checking last mod actions...",bcolors.WARNING,logging.DEBUG)
    PostsLeft = await AllowNewAccount(subreddit, submission.author, 0)
    if PostsLeft == 0:
        ReApproveUser(submission.author.name)
        Log(f"User {submission.author.name} re-approved",bcolors.OKGREEN,logging.INFO)
    else:
        Log(f"Troublesome User {submission.author.name} has been reported to the modqueue, {PostsLeft} posts left",bcolors.WARNING,logging.INFO)
        await submission.report(f"Usuario Problematico por otros {PostsLeft} posteos")

if __name__ == "__main__":
    asyncio.Task(main())
    loop = asyncio.get_event_loop()
    loop.run_forever()