# bot.py
import os
import sqlite3 as sl
import discord
import praw
from prawcore.exceptions import OAuthException, ResponseException
from dotenv import load_dotenv
from Reddit import get_reddit_object
from datetime import datetime
from datetime import timedelta, date

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
client = discord.Client()
con = sl.connect(os.getenv('DB'))
rres = get_reddit_object()
if rres['status'] == 'success':
    reddit = rres['data']
else:
    print(rres['data'])

@client.event
async def on_ready():
    print(f'{client.user.name} has connected to Discord!')

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    SenderAction = CheckSender(con,message.author)
    if SenderAction['modID'] != '0':
        if message.content.lower().startswith('warns '):
            Response = GetWarns(con,message.content[6:].strip(' '))
        elif message.content.lower().startswith('unwarn '):
            Response = Unwarn(con,message.content[7:].strip(' '))
        elif message.content.lower().startswith('unban '):
            Response = Unban(message.content[6:].strip(' '), reddit)
        else:
            if SenderAction['status'] == '0':
                Response = InitAction(message.content, con, reddit, SenderAction)
            else:
                linkType = GetLinkType(message.content)
                if linkType != 0:
                    DeletePending(con,SenderAction['status']) #el mod mando otro link en vez de responder, borrar lo pendiente y hacer uno nuevo
                    Response = InitAction(message.content, con, reddit, SenderAction)
                else:
                    Response = ResolveAction(con, message.content, SenderAction['status'], reddit)
        con.commit()
        await message.channel.send(Response)
    if message.content == 'raise-exception':
        raise discord.DiscordException
def SanatizeRedditLink(sIn):
    sIn = sIn.lstrip('http')
    sIn = sIn.lstrip('s')
    sIn = sIn.lstrip('://')
    sIn = sIn.lstrip('www.')
    sIn = sIn.lstrip('old.') 
    if sIn.startswith('reddit.com') and os.getenv('subreddit').lower() in sIn.lower():
        sIn.rstrip('/')
        chunks = sIn.split("/?")
        afterlastslash = 0
        if(len(chunks) > 1):
            afterlastslash = len(chunks[len(chunks) -1]) + 2 
        if afterlastslash > 0:
            sIn = sIn[:afterlastslash * -1]
        sIn = sIn.rstrip('/')
        return sIn
    return ''
def GetLinkType(sIn):
    sIn = SanatizeRedditLink(sIn)
    chunks = sIn.split('/')
    if len(chunks) == 0:
        return 0 #invalid link
    if len(chunks) == 6:
        return 1 #link/post
    if len(chunks) == 7:
        return 2 #comment
    return 0 
def Unban(sUser, reddit):
    sub = reddit.subreddit(os.getenv('subreddit'))
    sub.banned.remove(sUser)
    return f"Usuario {sUser} ha sido desbanneado."

def Unwarn(con,sId):
    if not sId.isnumeric():
        return "Id Incorrecto"
    iId = int(sId)
    rows = GetActionDetail(con, '', iId,'')
    if len(rows) > 0:
        con.execute(f"DELETE FROM Actions WHERE Id = {iId}")
        return f"Warn #{iId} eliminado."
    return f"Warn #{iId} no encontrado."

def GetWarns(con,sUser):
    rows = GetActionDetail(con, '', 0,sUser)
    sRetu = ''
    for row in rows:
        sRetu = sRetu + f"Warn Id: {row['Id']} \nMod: {row['ModName']} \nFecha: {row['Date']} \nLink: {row['Link']}\nMotivo: {row['TypeDesc']}\nDetalles: {row['Details']}\n--------------------\n"
    if len(sRetu) == 0:
        sRetu = f"No se encontaron warns para el usuario {sUser}"
    return sRetu

def CheckSender(con, author):

    cur = con.cursor()
    cur.execute(f"SELECT Id FROM Moderators WHERE DiscordID = {author.id}")
    rows = cur.fetchall()
    if len(rows) <= 0:
        return {'modID': '0', 'status': '0'} #not valid 
    modId = rows[0][0]
    cur.execute(f"SELECT Id FROM Actions WHERE Mod = {modId} and ActionType is null")
    rows = cur.fetchall()
    if len(rows) <= 0:
        return {'modID': modId, 'status': '0'} #nothing pending
    else:
        return {'modID': modId, 'status': rows[0][0]} # Pending resolution

def GetActionTypes(con):
    data = con.execute("SELECT * FROM ActionType")
    sRetu = ""
    for row in data:
        sRetu = f"{sRetu} {row[0]} - {row[1]}\n"
    return sRetu
def DeletePending(con, Id):
    con.execute(f"DELETE FROM Actions WHERE Id = {Id}")

def ValidateActionType(con, Id):
    cur = con.cursor()
    cur.execute(f"SELECT Id FROM ActionType WHERE Id = {Id}")
    rows = cur.fetchall()
    return len(rows) > 0

def SanatizeInput(sIn):
    sOut = sIn.split('-')
    sDesc = ''
    if len(sOut) > 1:
        sDesc = sIn[len(sOut[0]):].strip('-').strip(' ')
    sId = sOut[0].strip('-').strip(' ')
    if(sId.isnumeric()):
        return {'Id': sId,'Description' : sDesc}
    else:
        return {'Id': '0','Description' : sDesc}

def GetApplyingPolicy(con, ActionId):
    cur = con.cursor()
    cur.execute(f"Select User FROM Actions WHERE Id = {ActionId}")
    rows = cur.fetchall()
    if len(rows) > 0:
        dateFrom = datetime.now() - timedelta(days=int(os.getenv('warnexpires')))
        cur.execute(f"Select Count(1) FROM Actions WHERE User = '{rows[0][0]}' and Date >= '{dateFrom}'")
        rows = cur.fetchall()
        cur.execute(f"Select Action, BanDays, Message FROM Policies WHERE [From] <= {rows[0][0]} and [To] >= {rows[0][0]}")
        rows = cur.fetchall()
        if len(rows) > 0:
            return {'Action':rows[0][0], 'BanDays': rows[0][1], 'Message':rows[0][2]}
    return  {'Action':'0', 'BanDays': '0', 'Message':'0'}

def CreateModMail(sMessage, Link, ActionDesc, Details):
    sMessage = sMessage.replace("[SUB]", os.getenv('subreddit'))
    sMessage = sMessage.replace("[LINK]", Link)
    sMessage = sMessage.replace("[ActioTypeDesc]", ActionDesc)
    sMessage = sMessage.replace("[Details]", Details.replace("\n",">\n"))
    sMessage = sMessage.replace("\\n", "\n")
    return sMessage

def ResolveAction(con, sIn, ActionId, reddit):
    Input = SanatizeInput(sIn)
    if ValidateActionType(con, Input['Id']):
        ApplyingPol = GetApplyingPolicy(con,ActionId)
        if ApplyingPol['Action'] > 0:
            con.execute(f"UPDATE Actions SET ActionType = {Input['Id']}, Description = '{Input['Description']}' WHERE Id = {ActionId};")
            ActionDetailRows = GetActionDetail(con, '', ActionId,'')
            ActionDetailRow = ActionDetailRows[0]
            modmail = CreateModMail(ApplyingPol['Message'], ActionDetailRow['Link'],ActionDetailRow['TypeDesc'],ActionDetailRow['Details'])
            LinkType = GetLinkType(f"https://{ActionDetailRow['Link']}")
            if LinkType == 1:
                praw.models.Submission(reddit,url = f"https://{ActionDetailRow['Link']}").mod.remove()
            else:
                praw.models.Comment(reddit,url = f"https://{ActionDetailRow['Link']}").mod.remove()
            if ApplyingPol['Action'] == 1: #Warn
                reddit.redditor(ActionDetailRow['User']).message(f"Equipo de Moderacion de /r/{os.getenv('subreddit')}",modmail, from_subreddit=os.getenv('subreddit'))
            if ApplyingPol['Action'] == 2: #Ban
                sub = reddit.subreddit(os.getenv('subreddit'))
                if int(ApplyingPol['BanDays']) > 0:
                    sub.banned.add(ActionDetailRow['User'],ban_reason=ActionDetailRow['TypeDesc'], duration=int(ApplyingPol['BanDays']), ban_message=modmail)
                    return f"Usuario banneado por {ApplyingPol['BanDays']} dias."
                sub.banned.add(ActionDetailRow['User'],ban_reason=ActionDetailRow['TypeDesc'], ban_message=modmail)
                return f"Usuario banneado permanentemente."
            return "Usuario advertido."
            #Aca va la parte en donde vemos que hacemos con las politicas
        return "Error al buscar politica"
    else:
        return "Formato incorrecto, por favor ingresa el motivo usando los IDs correspondientes"

def GetActionDetail(con, Link, ActionId, User):
    sQuery = f"SELECT m.RedditName, t.Description, a.Description, a.Date, a.Link, a.User, a.Id FROM Actions a join Moderators m on m.Id = a.Mod join ActionType t on t.Id = a.ActionType "
    cur = con.cursor()
    if ActionId > 0:
        sQuery = sQuery + f"WHERE a.Id = '{ActionId}'"
    elif len(Link) > 0:
        sQuery = sQuery + f"WHERE a.Link = '{SanatizeRedditLink(Link)}'"
    elif len(User) > 0:
        sQuery = sQuery + f"WHERE lower(a.User) = '{User.lower()}'"
    cur.execute(sQuery)
    rows = cur.fetchall()
    lst = []
    for row in rows:
        lst.append({'ModName':row[0], 'TypeDesc': row[1], 'Details':row[2], 'Date':row[3], 'Link':row[4], 'User':row[5], 'Id': row[6]})
    return lst

def InitAction(Link, con, reddit, SenderAction):
    linkType = GetLinkType(Link)
    if linkType == 0:
        return 'link invalido'
    else:
        rows = GetActionDetail(con, Link, 0,'')
        if len(rows) > 0:
            return f"Ese link ya fue sancionado por Mod: {rows[0]['ModName']} \nFecha: {rows[0]['Date']} \nMotivo: {rows[0]['TypeDesc']}\nDetalles: {rows[0]['Details']}"
        else:
            if linkType == 1:
                submission = praw.models.Submission(reddit,url = Link)
                AuthorName = submission.author.name
            else:
                comment = praw.models.Comment(reddit,url = Link)
                AuthorName = comment.author.name  # This returns a ``Redditor`` object.
            row = (AuthorName, SanatizeRedditLink(Link), SenderAction['modID'],datetime.now() )
            con.execute("""INSERT INTO Actions (User, Link, Mod, Date) VALUES (?,?,?,?);""", row)
            return f"Selecciona un motivo (# - Descripcion <Opcional>) \n{GetActionTypes(con)}"
client.run(TOKEN)