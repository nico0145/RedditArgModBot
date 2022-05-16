import os
import asyncpraw
import json
import logging
import dotenv
from datetime import timedelta, date, datetime
from dateutil.relativedelta import *
from prawcore.exceptions import OAuthException, ResponseException
from types import SimpleNamespace
from py.DiscordHandle import *
import psutil
class LastModmailChecked:
    def __init__(self, sub, lastUpd):
        self.Subreddit = sub
        self.LastUpdated = lastUpd
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
class UserStatus:
    def __init__(self,Id, Roles, PendingAction):
        self.Id = Id
        self.Roles = Roles
        self.PendingAction = PendingAction
class ExecuteActionException(Exception):
    def __init__(self, custom_code):
        Exception.__init__(self)
        self.custom_code = custom_code
class Process:
    def __init__(self,name,val):
        self.Name=name
        self.Id = val
    def cssClass(self):
        if self.Running:
            return "running" 
        return "dead"
async def CommonGetRedditObject(UsesUsernamePwd, refreshToken, redirectUri,userAgent):
    try:
        app_key = os.getenv('app_key')
        app_secret = os.getenv('app_secret')
        if UsesUsernamePwd:
            username = userAgent = os.getenv('USUARIO')
            password = os.getenv('password')
            reddit = asyncpraw.Reddit(client_id=app_key,
                            client_secret=app_secret,
                            username=username,
                            password=password,
                            user_agent=userAgent)
            await reddit.user.me()
        elif refreshToken is not None:
            reddit = asyncpraw.Reddit(client_id=app_key,
                            client_secret=app_secret,
                            refresh_token=refreshToken,
                            user_agent=userAgent)
            await reddit.user.me()
        else:
            reddit = asyncpraw.Reddit(client_id=app_key,
                     client_secret=app_secret,
                     redirect_uri=redirectUri,
                     user_agent=userAgent)
        return {'status': 'success', 'data': reddit}

    except OAuthException as err:
        return {'status': 'error', 'data': 'Error: Unable to get API access, please make sure API credentials are correct and try again (check the username and password first)'}

    except ResponseException as err:
        return {'status': 'error', 'data': 'Error: ResponseException: ' + str(err)}

    except Exception as err:
        return {'status': 'error', 'data': 'Unexpected Error: ' + str(err)} 

async def async_get_reddit_object():
    return await CommonGetRedditObject(True,None,None,None)
async def async_get_reddit_object_Token(refreshToken,userAgent):
    return await CommonGetRedditObject(False,refreshToken,None,userAgent)
async def async_get_default_reddit_object(redirectUri,userAgent):
    return await CommonGetRedditObject(False,None,redirectUri,userAgent)

def GetSchedPostsFromWiki(wiki):
    return json.loads(wiki.content_md.replace("\t","").replace("\n",""),object_hook=lambda d: SimpleNamespace(**d))
def InitializeLog(fileName):
    if os.name == 'nt': # Only if we are running on Windows
        from ctypes import windll
        k = windll.kernel32
        k.SetConsoleMode(k.GetStdHandle(-11), 7)
    logging.basicConfig(filename=fileName, encoding='utf-8', format='[%(asctime)s] %(message)s',  level=logging.INFO)
def Log(Text,color,level):
    print(f"{color}{Text}{bcolors.ENDC}\n------")
    logging.log(level,Text)
def ReplaceStringFormat(sIn):
    sIn = sIn.replace('[FechaCorta]', datetime.utcnow().strftime('%d/%m'))
    return sIn
def DeletePending(DB, Id):
    DB.WriteDB(f"DELETE FROM Actions WHERE Id = {Id}")
async def PostSchedPost(DB, reddit, subreddit, schedPost):
    Log(f"Posting in r/{subreddit.display_name} ID: {schedPost.Id} - Next Date: {schedPost.nextTime}",bcolors.OKCYAN,logging.INFO)
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
            await VerifyUnstickyReplace(DB, reddit,subreddit.display_name)
        row = (schedPost.Id,datetime.utcfromtimestamp(post.created_utc).strftime('%Y-%m-%d %H:%M:%S.%f'),post.id, schedPost.TimeLenght > 0, subreddit.display_name)
        await SaveSchedPost(DB, row)
        return True
    else:
        Log(f"Error while posting scheduled post: flair {schedPost.Flair} not found",bcolors.WARNING,logging.WARNING)
        return False
def SanatizeInput(sIn):
    sOut = sIn.split(',')
    sDesc = ''
    if len(sOut) > 1:
        sDesc = sIn[len(sOut[0]):].strip(',').strip(' ')
    sId = sOut[0].strip(',').strip(' ')
    if sId.startswith('!'):
        sId = sId[1:]
        if(sId.isnumeric()):
            return {'Id': sId,'Description' : sDesc}
    return {'Id': '0','Description' : sDesc}
def ValidateActionType(DB, Id):
    rows = DB.ExecuteDB(f"SELECT Weight FROM ActionType WHERE Id = {Id} and Active = 1")
    if len(rows) > 0:
        return int(rows[0][0])
    return -1
async def SaveSchedPost(DB, row):
    DB.WriteDB("""INSERT INTO ScheduledPosts (RedditID,PostedDate, PostID, IsStickied,Subreddit) VALUES (?,?,?,?,?);""", row)
async def VerifyUnstickyReplace(DB, reddit, sSub):
    StickiedPosts = DB.ExecuteDB(f"select PostID from ScheduledPosts where IsStickied = 1 and Subreddit = '{sSub}'")
    for postID in StickiedPosts:
        Post = await reddit.submission(postID[0])
        if Post.stickied == False:
            DB.WriteDB(f"Update ScheduledPosts set IsStickied = false where PostID = '{postID[0]}'")
            Log(f"Post ID: {postID[0]} - Sticky was replaced.",bcolors.OKCYAN,logging.INFO)
def ifnull(var, val):
  if var is None:
    return val
  return var
def GetCommonActionDetails(DB, Criteria, Value, GetModmailId=True):
    #The first piece of the query is to find stuff based on discord actions, the second piece (after union) is to find stuff based on reddit actions
    sModmailField = sModmailJoin = ""
    if GetModmailId:
        sModmailField = ", MM.modmailID "
        sModmailJoin = "left join Modmails MM on MM.ActionId = A.Id "
    sQuery = "select * from (SELECT m.Name, t.Description, " \
            "		ifnull(NULLIF(a.Description, ''), ifnull(t.DefaultMessage,'')), a.Date, a.Link, D.Name as UserName, a.Id, t.Weight,  " \
            f"			'<@' ||  m.DiscordID ||  '>', a.Snapshot, ifnull(t.RuleLink,''){sModmailField}  " \
            "FROM Actions a  " \
            "join DiscordUsers D on D.Id = A.DiscordUserId  " \
            "join DiscordRedditUser DRU on DRU.DiscordId = A.DiscordUserId " \
            "join RedditUsers R on R.Id = DRU.RedditId " \
            "join DiscordUsers m on m.Id = a.Mod  " \
            f"left join ActionType t on t.Id = a.ActionType  {sModmailJoin}" \
            "[Criteria] " \
            "union " \
            "SELECT m.Name, t.Description, " \
            "		ifnull(NULLIF(a.Description, ''), ifnull(t.DefaultMessage,'')), a.Date, a.Link, R.RedditName as UserName, a.Id, t.Weight,  " \
            f"		'<@' ||  m.DiscordID ||  '>', a.Snapshot, ifnull(t.RuleLink,''){sModmailField}  " \
            "FROM Actions a  " \
            "left join DiscordRedditUser DRU on DRU.RedditId = A.RedditUserId " \
            "left join DiscordUsers D on D.Id = DRU.DiscordId  " \
            "join RedditUsers R on R.Id = A.RedditUserId  " \
            "join DiscordUsers m on m.Id = a.Mod  " \
            f"left join ActionType t on t.Id = a.ActionType  {sModmailJoin}" \
            "[Criteria] ) order by date"
    if Criteria == "ActionId":
        sQuery = sQuery.replace("[Criteria]", f"WHERE a.Id = {Value}")
    elif Criteria == "Link":
        sQuery = sQuery.replace("[Criteria]", f"WHERE a.Link = '{Value}'")
    elif Criteria == "DiscordId":
        sQuery = sQuery.replace("[Criteria]", f"WHERE D.DiscordId = {Value}")
    elif Criteria == "RedditName":
        sQuery = sQuery.replace("[Criteria]", f"WHERE lower(R.RedditName) = '{Value.lower()}'")
    rows = DB.ExecuteDB(sQuery)
    lst = []
    for row in rows:
        modmailID = ""
        if GetModmailId:
            modmailID = row[11]
        lst.append({'ModName':row[0], 'TypeDesc': row[1], 'Details':row[2], 'Date':row[3], 'Link':row[4], 'User':row[5], 'Id': row[6], 'Weight': row[7], 'DiscordId': row[8], 'Snapshot':row[9], 'RuleLink':row[10], 'ModmailID':modmailID})
    return lst
def GetCommonActionDetail(DB, Criteria, Value):
    aDs = GetCommonActionDetails(DB, Criteria, Value)
    if len(aDs) > 0:
        return aDs[0]
    return None
def IsValidSubLink(sIn, DB):
    sSub = GetValidSubByLink(sIn, DB)
    return sSub is not None
def GetValidSubByLink(sIn, DB):
    chunks = sIn.split('/')
    subs = DB.GetSetting("subreddit") #Checked
    lstInter = [value for value in chunks if value in subs]
    if len(lstInter) > 0:
        return lstInter[0]
    return None
def GetDefaultSubByLink(sIn, DB):
    sSub = GetValidSubByLink(sIn, DB)
    if sSub is None:
        sSub = DB.GetSetting("subreddit")[0] #checked
    return sSub
async def CreateModMail(sMessage, Link, ActionDesc, Details, sUser, RuleLink, Snapshot,reddit, DB):
    try:
        sSub = GetDefaultSubByLink(Link, DB)
        sMessage = sMessage.replace("[Sub]", sSub)
        if "reddit" not in Link:
            if "[Link]" not in sMessage:
                sMessage = sMessage.replace("[Details]", "[Details]\n\n"+Snapshot)
            else:
                sMessage = sMessage.replace("[Link]", Snapshot)
        else:
            sMessage = sMessage.replace("[Link]", Link)
        sActionDesc = ActionDesc
        if len(RuleLink) > 0:
            sActionDesc = f"[{sActionDesc}]({RuleLink})"
        sMessage = sMessage.replace("[ActionTypeDesc]", sActionDesc)
        sMessage = sMessage.replace("[Details]", Details.replace("\n",">\n"))
        if "[Consultas]" in sMessage:
            sConsultas = await GetLastConsultasThread(reddit, DB, sSub)
            sMessage = sMessage.replace("[Consultas]", sConsultas)
        if "[Summary]" in sMessage:
            sMessage = sMessage.replace("[Summary]", GetWarnsUserReport(sUser,1000- (len(sMessage) - len("[Summary]")),DB))
        sMessage = sMessage.replace("\\n", "\n")
        return sMessage[:1000]
    except:
        raise
async def GetLastConsultasThread(reddit, DB, sSub):
    List = ""
    sub = await reddit.subreddit("argentina") #hardcodeado porque todas las submisiones de preguntas van aca #ya no, hijos de puta :D
    #Submissions = await reddit.subreddit(sSub).search(query='author:Robo-TINA AND (title:Consultas OR title:Preguntas)',sort='new',limit=1)
    async for Submission in sub.search(query='author:Robo-TINA AND (title:Consultas OR title:Preguntas)',sort='new',limit=1):
        List += Submission.shortlink
    return List
def GetWarnsUserReport(sUser, msgLen, DB):
    rows = GetCommonActionDetails(DB, "RedditName", sUser,False)
    sRetu = ""
    dateFrom = datetime.now() - timedelta(days=int(DB.GetSetting("warnexpires")))
    iWeight = 0
    for row in rows:
        if datetime.strptime(row['Date'], '%Y-%m-%d %H:%M:%S.%f') >= dateFrom and ifnull(row['Weight'],0) > 0:
            sRetu = f"{sRetu}{row['Date'].split(' ')[0]}\t"
            if 'reddit.com' in row['Link']:
                sRetu = f"{sRetu}[{row['TypeDesc']}](https://{row['Link']})\t"
            else:
                sRetu = f"{sRetu}{row['TypeDesc']} (Discord)\t"
            sRetu = f"{sRetu}Puntos: {row['Weight']}\n\n"
            iWeight += row['Weight']
    sRetu = sRetu.rstrip("\n") + f" **<-- Nueva Falta**\n\n**Total**: {iWeight}"
    while len(sRetu) > msgLen and len(sRetu) > 0:
        sRetu = sRetu[sRetu.find("\n") + 2:]
    return sRetu
def GetDiscordUser(DB, UserName):
    return DB.GetDBValue("select DRU.DiscordId from DiscordRedditUser DRU " \
                         "join RedditUsers R on R.Id = DRU.RedditId " \
                         f"where R.RedditName = '{UserName}'")
def SaveDiscordMute(DB, dateFrom, mBanDays, DuId, Performed, ActionID = None):
    BannedTo = datetime.timestamp(dateFrom  + relativedelta(days=+mBanDays))
    EditRow = DB.ExecuteDB(f"select ID, [To] from MutedUsers where DiscordId = {DuId} and [To] > {datetime.timestamp(datetime.now())}")
    if any(EditRow):
        if EditRow[0][1] < BannedTo:
            sExtraCols = ""
            if Performed is not None:
                sExtraCols = f"{sExtraCols}[Performed] = {Performed}, "
            if ActionID is not None:
                sExtraCols = f"{sExtraCols}[ActionID] = {ActionID}, "
            DB.WriteDB(f"Update MutedUsers set {sExtraCols}[To] = {BannedTo} where Id = {EditRow[0][0]};")
    else:
        sExtraCols = ""
        lstParams = [DuId, datetime.timestamp(datetime.now()), BannedTo]
        if Performed is not None:
            sExtraCols = f"{sExtraCols}, [Performed]"
            lstParams.append(Performed)
        if ActionID is not None:
            sExtraCols = f"{sExtraCols}, [ActionID]"
            lstParams.append(ActionID)
        Params = tuple(lstParams)
        DB.WriteDB(f"Insert into MutedUsers (DiscordId, [From], [To]{sExtraCols}) values({','.join('?' for mParam in lstParams)});",Params)
async def NotifyRedditUser(DB, reddit, preparedAction, ApplyingPol, ActionId, Source):
    ActionDetailRow = preparedAction["ActionDetailRow"]
    modmail = preparedAction["ModMail"]
    sDefSub = GetDefaultSubByLink(ActionDetailRow['Link'].lower(),DB)
    sReturn = ""
    if ApplyingPol['Action'] == 2: #Only send multiple modmails if the warn applies Ban
        sSubs = DB.GetSetting("subreddit") #Checked
        if Source == "Reddit":
            DUID = GetDiscordUser(DB,ActionDetailRow['User']) #also ban on discord
            if DUID is not None:
                SaveDiscordMute(DB, datetime.now(), int(ApplyingPol['BanDays']), DUID, 0, ActionId)
                sReturn = f"Discord: Usuario banneado por {ApplyingPol['BanDays']} dias.\n"
    else:
        sSubs = [sDefSub]
    for sSubReddit in sSubs:
        sReturn = f"{sReturn}r/{sSubReddit}:"
        oSubReddit = await reddit.subreddit(sSubReddit)
        isMuted = False
        async for mutedUser in oSubReddit.muted():
            if mutedUser.name == ActionDetailRow['User']:
                isMuted = True
                MutedRelationship = mutedUser
        if isMuted:
            await oSubReddit.muted.remove(MutedRelationship)
        if ApplyingPol['Action'] == 1: #Warn
            objModmail = await oSubReddit.modmail.create(subject = f"Equipo de Moderacion de /r/{sDefSub}",body = modmail, recipient = ActionDetailRow['User'],author_hidden = True)
            UpdateModmailId(DB, objModmail.id, ActionId)
            await objModmail.archive()
            sReturn = f"{sReturn} Usuario Advertido.\n"
        if ApplyingPol['Action'] == 2: #Ban
            sRet = await BanRedditUser(oSubReddit,ApplyingPol['BanDays'],ActionDetailRow, modmail, ActionId)
            #lastMessages = await oSubReddit.modmail.conversations(sort="mod", state="archived", limit=1)
            async for lastMessage in oSubReddit.modmail.conversations(sort="mod", state="archived", limit=1):
                #lastMessage.load()
                if lastMessage.participant.name == ActionDetailRow['User']:
                    UpdateModmailId(DB,lastMessage.id, ActionId)
                else:
                    sRet += " - No se pudo enviar mod mail."
            sReturn = f"{sReturn} {sRet}\n"
        if isMuted:
            await oSubReddit.muted.add(MutedRelationship)
    return sReturn
def getProcessStatus():
    listName = ['WebIFPID', 'AutoModPID', 'DiscordModPID', 'RedditModPID']
    listProcess = []
    dotenv.load_dotenv(override=True)
    for name in listName:
        val = os.getenv(name)
        if val is not None:
            listProcess.append(Process(name,val))
    for process in listProcess:
        process.Running = psutil.pid_exists(int(process.Id))
    return listProcess
async def BanRedditUser(sub,BanDays,ActionDetailRow, modmail, ActionId):
    try:
        if int(BanDays) > 0:
            await sub.banned.add(ActionDetailRow['User'],ban_reason=ActionDetailRow['TypeDesc'], duration=int(BanDays), ban_message=modmail)
            return f"Usuario banneado por {BanDays} dias."
        await sub.banned.add(ActionDetailRow['User'],ban_reason=ActionDetailRow['TypeDesc'], ban_message=modmail)
        return f"Usuario banneado permanentemente."
    except: 
        return f"Ocurrio un error al intentar bannear al usuario: {sys.exc_info()[1]}"
def UpdateModmailId(DB,modmailId, ActionId):
    DB.WriteDB(f"insert into Modmails(ActionId,modmailID) values({ActionId},'{modmailId}');")
def ConfirmedUnwarn(DB,iId):
    DB.WriteDB(f"DELETE FROM Actions WHERE Id = {iId}")
    return [Message(False,False,MessageType.Text,f"Warn #{iId} eliminado.")]