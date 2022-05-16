import os
import sqlite3 as sl
import discord
import asyncpraw
import sys
import asyncio
import threading
from prawcore.exceptions import OAuthException, ResponseException
from dotenv import load_dotenv
import dotenv
from Reddit import get_reddit_object
from datetime import timedelta, date, datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from dateutil.relativedelta import *
from py.DBHandle import *
from py.DiscordHandle import *
from py.StaticHelpers import *

class UserSubmission:
    def __init__(self,Type, created_utc, score, removed):
        self.Type = Type
        self.Created = created_utc
        self.score = score
        self.removed = removed

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
client = discord.Client()
DB = DBHandle(os.getenv('DB'))
reddit = None
async def CheckModmail():
    modmails = [LastModmailChecked(sSub.lower(),"") for sSub in DB.GetSetting("subreddit")]
    while True:
        try:
            for modmailbox in modmails:
                asyncio.Task(CheckModmailBox(modmailbox))
            seconds = int(DB.GetSetting("RefreshModMail"))
            if seconds > 0:
                await asyncio.sleep(seconds)
        except:
            Log(f"An error occurred while trying to get modmails from Reddit's API: {sys.exc_info()[1]}",bcolors.WARNING,logging.ERROR)
async def CheckModmailBox(modmailbox):
    sub = await reddit.subreddit(modmailbox.Subreddit)
    sQuery = ""
    mlastUpd = ""
    try:
        async for mail in sub.modmail.conversations():
            if mail.last_updated > modmailbox.LastUpdated:
                Log(f"[r/{modmailbox.Subreddit}] New modmail ID {mail.id} received at {mail.last_updated}",bcolors.OKGREEN,logging.INFO)
                if mail.last_mod_update is None or (mail.last_user_update is not None and  mail.last_mod_update < mail.last_user_update):
                    sQuery += f" or (MM.modmailID = '{mail.id}' and ifnull(MM.LastModmailUpdated,'{mail.last_user_update}')  <= '{mail.last_user_update}')"
                if mail.last_updated > mlastUpd:
                        mlastUpd = mail.last_updated
    except:
        Log(f"An error occurred while reading modmails ({mail.id}) from Reddit's API: {sys.exc_info()[1]}",bcolors.WARNING,logging.ERROR)
        mlastUpd = modmailbox.LastUpdated
    if mlastUpd > modmailbox.LastUpdated:
        modmailbox.LastUpdated = mlastUpd
    if len(sQuery) > 0:
        sQuery =  "select R.RedditName, '<@' ||  m.DiscordID ||  '>', 'https://mod.reddit.com/mail/inbox/'|| MM.modmailID,'https://'|| a.Link, at.Description, a.Id, MM.LastModmailUpdated, MM.modmailID " \
                    "from Actions a join RedditUsers R on R.Id = A.RedditUserId join Modmails MM on MM.ActionId = A.Id join DiscordUsers m on m.Id = a.Mod join ActionType at on at.Id = a.ActionType join UserRoles UR on UR.DiscordId = m.Id join Roles RL on RL.Id = UR.RoleId " \
                    f"where RL.Name = 'Reddit Mod' and {sQuery[4:]}"
        rows = DB.ExecuteDB(sQuery)
        #print(f"Query: '{sQuery}'\nDB Matches: {len(rows)}\n")
        if len(rows) > 0:
            channel = client.get_channel(int(DB.GetSetting("GaryChannel")))
            if len(rows) > 1:
                Log(f"multiple modmail responses using the following query:\n{sQuery}",bcolors.WARNING,logging.WARNING)
        for row in rows:
            #print(f"{row[1]}: {row[0]} Respondio al modmail generado por:\n{row[3]}\nSancion: {row[4]}\nClickea en el siguiente link para responder\n{row[2]}\nLastModmailUpdated: {row[6]}\nQuery criteria: [{sQuery}")
            embMsg = discord.Embed()
            embMsg.description = f"[u/{row[0]}](https://www.reddit.com/user/{row[0]}/) Respondio al modmail generado por:\n[{row[4]}]({row[3]})\nClickea [Aqui]({row[2]}) para responder"
            sentMsg = await channel.send(row[1], embed=embMsg)
            DB.WriteDB(f"Update Modmails set LastModmailUpdated = '{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f+00:00')}' WHERE modmailID = '{row[7]}'")
@client.event
async def on_ready():
    InitializeLog(os.getenv('RedditBotLog'))
    envFile = os.path.join(os.path.dirname(os.path.abspath(__file__)) + os.path.sep, '.env')
    dotenv.set_key(envFile,"RedditModPID",str(os.getpid()))
    Log(f"Reddit mod bot connected to Discord using discord user {client.user.name}",bcolors.OKGREEN,logging.INFO)
    rres = await async_get_reddit_object()
    if rres['status'] == 'success':
        global reddit
        reddit = rres['data']
        rUser = await reddit.user.me()
        Log(f"Reddit mod bot connected to Reddit using user {rUser.name}",bcolors.OKGREEN,logging.INFO)
        await CheckModmail()
        loop = asyncio.get_event_loop()
        loop.run_forever()
    else:
        Log(f"Reddit mod bot couldn't connect to Reddit, status returned: {rres['status']}",bcolors.OKGREEN,logging.ERROR)

@client.event
async def on_message(message):
    Response = []
    if message.author == client.user or message.channel.id == 929080844407164988: #!=820103550305828884:
        return
    SenderAction = CheckSender(message.author)
    if 'Bot User' in SenderAction.Roles or 'Admin' in SenderAction.Roles: 
        StandardMessage = message.content.lower()
        if StandardMessage.strip(' ')=="gary":
            Response = [Message(False,False,MessageType.Text,"gary - Muestra esta ayuda\nwarns <user> - Muestra los warns de un usuario\nunwarn <id> - Elimina un warn especifico\nunban <user> - desbannea a un usuario\napproveuser <user> - Agrega a un usuario a la lista de usuarios aprobados\nusers - funciones de usuarios\nroles - funciones de roles\nsettings - configura las preferencias\npolicies - configura las politicas de moderacion\nreasons - configura los motivos de sancion\nstats - Muestra estadisticas de moderacion\nschedposts - Muestra los posts programados\n<link> - inicia el proceso de warn")]
        elif StandardMessage.startswith('warns '):
            Response = GetWarns(message.content[6:].strip(' '))
        elif StandardMessage.startswith('unwarn '):
            Response = Unwarn(message.content[7:].strip(' '), SenderAction.Roles)
        elif StandardMessage.startswith('unban '):
            if 'Reddit Mod' in SenderAction.Roles: 
                Response = await Unban(message.content[6:].strip(' '), reddit)
            else:
                Response = [Message(False,False,MessageType.Text,"Se requiere del rol Reddit Mod para remover bans.")]
        elif StandardMessage.startswith('approveuser '):
            if 'Reddit Mod' in SenderAction.Roles: 
                Response = await ApproveUser(message.content[11:].strip(' '), reddit)
            else:
                Response = [Message(False,False,MessageType.Text,"Se requiere del rol Reddit Mod para aprobar usuarios.")]
            #MassSanatizeLinks() this is here if we need to run a mass sanatization if reddit changes the URL formats or something
        elif StandardMessage.startswith('users'):
            Response = HandleUsers(message.content[6:].strip(' '),SenderAction.Roles)
        elif StandardMessage.startswith('settings'):
            Response = HandleSettings(message.content[9:].strip(' '), SenderAction.Roles)
        elif StandardMessage.startswith('roles'):
            Response = HandleRoles(message.content[9:].strip(' '))
        elif StandardMessage.startswith('policies'):
            Response = HandlePolicies(message.content[9:].strip(' '),SenderAction.Roles)
        elif StandardMessage.startswith('reasons'):
            Response = HandleReasons(message.content[8:].strip(' '),SenderAction.Roles)
        elif StandardMessage.startswith('stats'):
            Response = await HandleStats(message.content[6:].strip(' '), SenderAction.Id, reddit)
        elif StandardMessage.startswith('schedposts'):
            if 'Reddit Mod' in SenderAction.Roles: 
                Response = await HandleSchedposts(message.content[10:].strip(' '), reddit)
            else:
                Response = [Message(False,False,MessageType.Text,"Se requiere del rol Reddit Mod para administrar posts recurrentes.")]
        elif StandardMessage.strip(' ')=="undo":
            if 'Reddit Mod' in SenderAction.Roles: 
                if not SenderAction.PendingAction is None:
                    DeletePending(DB, SenderAction.PendingAction)
                    Response = [Message(False,False,MessageType.Text,f"WarnID {SenderAction.PendingAction} pendiente eliminado.")]
                else:
                    Response = [Message(False,False,MessageType.Text,"No hay warnings pendientes.")]
        elif 'Reddit Mod' in SenderAction.Roles: 
            ActionableMessage = message.content.split('!')
            linkType = GetLinkType(ActionableMessage[0])
            if linkType != 0:
                if SenderAction.PendingAction is not None:
                    DeletePending(DB, SenderAction.PendingAction) #el mod mando otro link en vez de responder, borrar lo pendiente y hacer uno nuevo
                if len(ActionableMessage)>1:
                    asyncio.Task(FullSanctionMessage(ActionableMessage,reddit,SenderAction,message))
                else:
                    Response = await InitAction(ActionableMessage[0], reddit, SenderAction)
            elif SenderAction.PendingAction is not None:
                Response = await ResolveAction(message.content, SenderAction.PendingAction, reddit,message)
        for IndResponse in Response:
            if IndResponse.To is None:
                destination = message.channel
            else:
                destination = message.author
            asyncio.Task(HandleMessage(int(os.getenv('DiscordMaxChars')),DB, destination,IndResponse))
            await asyncio.sleep(1)


    if message.content == 'raise-exception':
        raise discord.DiscordException
async def FullSanctionMessage(ActionableMessage,reddit,SenderAction,message):
    sLink = ActionableMessage[0]
    Response = await InitAction(ActionableMessage[0], reddit, SenderAction)
    SenderAction = CheckSender(message.author)
    if SenderAction.PendingAction is not None:
        Response = await ResolveAction(message.content[len(sLink):], SenderAction.PendingAction, reddit,message)
    for IndResponse in Response:
        await HandleMessage(int(os.getenv('DiscordMaxChars')),DB, message.channel ,IndResponse)
def SanatizeRedditLink(sIn):
    sIn = sIn.lstrip('http')
    sIn = sIn.lstrip('s')
    sIn = sIn.lstrip('://')
    sIn = sIn.lstrip('www.')
    sIn = sIn.lstrip('old.') 
    if (sIn.startswith('reddit.com') and (IsValidSubLink(sIn.lower(), DB) or 'message' in sIn.lower())) or sIn.startswith('mod.reddit.com/mail'):
        sIn = sIn.rstrip('/')
        chunks = sIn.split("?")
        afterlastslash = 0
        if(len(chunks) > 1):
            afterlastslash = len(chunks[len(chunks) -1]) + 1 
        if afterlastslash > 0:
            sIn = sIn[:afterlastslash * -1]
        sIn = sIn.rstrip('/')
        chunks = sIn.split('/')
        if len(chunks) == 7 or len(chunks) == 6:
            chunks[5] = "_"
            sIn = '/'.join(chunks)
        return sIn
    return ''
def HandleReasons(sCommand, UserRoles):
    if sCommand.lower().startswith('list'):
        return GetReasons()
    if sCommand.lower().startswith('edit '):
        if 'Bot Config' in UserRoles: 
            return EditReason(sCommand[4:].strip(' '))
        else:
            return [Message(False,False,MessageType.Text,"Se requiere del rol Bot Config para modificar motivos.")]
    if sCommand.lower().startswith('remove '):
        if 'Bot Config' in UserRoles: 
            return RemoveReason(sCommand[6:].strip(' '))
        else:
            return [Message(False,False,MessageType.Text,"Se requiere del rol Bot Config para remover motivos.")]
    if sCommand.lower().startswith('setdefaultmessage '):
        if 'Bot Config' in UserRoles: 
            return DefaultMessageReason(sCommand[17:].strip(' '))
        else:
            return [Message(False,False,MessageType.Text,"Se requiere del rol Bot Config para editar los mensajes por defecto.")]
    if sCommand.lower().startswith('setrulelink '):
        if 'Bot Config' in UserRoles: 
            return DefaultMessageReason(sCommand[17:].strip(' '))
        else:
            return [Message(False,False,MessageType.Text,"Se requiere del rol Bot Config para editar los links a las reglas.")]
    else:
        return [Message(False,False,MessageType.Text,"reasons list - Muestra un listado de los motivos\nreasons remove <id> - Elimina un motivo\nreasons edit <id (entero, si esta vacio es un nuevo registro)>,<Descripcion(texto)>,<Peso(entero)> - Agrega o edita un motivo\nreasons setdefaultmessage <id (entero)>,<Descripcion(texto)> - Agrega (o quita si esta vacio) un mensaje por defecto a los motivos\nreasons setrulelink <id (entero)>,<link(texto)> - Agrega (o quita si esta vacio) un link a la regla referenciada")]
def DefaultMessageReason(sCommand):
    return EditReasonProperty(sCommand, 'DefaultMessage', 'Motivo')
def RuleLinkReason(sCommand):
    return EditReasonProperty(sCommand, 'RuleLink', 'Link')
def EditReasonProperty(sCommand, Property, PropertyDesc):
    sCommand = sCommand.replace("\,","[Coma]")
    sParams = sCommand.split(',')
    if len(sParams) == 2 and check_int(sParams[0].strip(' ')):
        sId = sParams[0].strip(' ')
        sDescription = sParams[1].replace("[Coma]",",").strip(' ')
        DB.WriteDB(f"Update ActionType set [{Property}] = '{sDescription}' where Id = {sId}")
        return [Message(False,False,MessageType.Text,f"{PropertyDesc} agregado")]
    return [Message(False,False,MessageType.Text,f"Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\n<id(entero)>,<Mensaje(texto)>\nPara insertar comas [,] en los campos de texto usar el caracter de escape \\\,")]

def EditReason(sCommand):
    sCommand = sCommand.replace("\,","[Coma]")
    sParams = sCommand.split(',')
    if len(sParams) == 3:
        if (len(sParams[0].strip(' ')) == 0 or check_int(sParams[0].strip(' '))) and len(sParams[1].strip(' ')) > 0 and check_int(sParams[2].strip(' ')):
            sId = sParams[0].strip(' ')
            sDescription = sParams[1].replace("[Coma]",",")
            Weight = sParams[2].strip(' ')
            row = (sDescription,Weight)
            if len(sId) == 0: #Agregar Motivo
                DB.WriteDB(f"""INSERT INTO ActionType ([Description], [Weight], Active) VALUES (?,?,1);""",row)
                return [Message(False,False,MessageType.Text,"Motivo agregado")]
            else: # Editar Motivo
                rows = DB.ExecuteDB(f"SELECT * FROM ActionType where Id = {sId} and Active = 1")
                if len(rows) > 0:
                    DB.WriteDB(f"Update ActionType set [Description] = ?, [Weight] = ? WHERE Id = {sId}", row)
                    return [Message(False,False,MessageType.Text,f"Motivo {sId} actualizado.")]
                return [Message(False,False,MessageType.Text,f"Motivo {sId} no encontrado.")]
    return [Message(False,False,MessageType.Text,f"Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\n<id(entero, si esta vacio es un nuevo registro)>,<Descripcion(texto)>,<Peso(entero)>\nPara insertar comas [,] en los campos de texto usar el caracter de escape \\\,")]
def RemoveReason(sId):
    if not check_int(sId):
        return [Message(False,False,MessageType.Text,"Id Incorrecto")]
    iId = int(sId)
    rows = DB.ExecuteDB(f"SELECT * FROM ActionType where Id = {iId}")
    if len(rows) > 0:
        DB.WriteDB(f"Update ActionType set Active = 0 WHERE Id = {iId}")
        return [Message(False,False,MessageType.Text,f"Motivo {iId} eliminado.")]
    return [Message(False,False,MessageType.Text,f"Motivo {iId} no encontrado.")]
def GetReasons():
    rows = DB.ExecuteDB(f"SELECT * FROM ActionType where Active = 1")
    sRetu = ""
    for row in rows:
        sRetu = sRetu + f"Id: {row[0]}\nDescription: {row[1]}\nPeso: {row[2]}\n--------------------\n"
    return [Message(False,False,MessageType.Text,sRetu)]

async def HandleSchedposts(sCommand, reddit):
    if sCommand.lower().startswith('list '):
        return await GetSchedPostList(reddit, sCommand[5:].strip(' ').lower())
    if sCommand.lower().startswith('details '):
        return await GetSchedPostDetails(reddit, sCommand[8:].strip(' ').lower())
    if sCommand.lower().startswith('post '):
        return await MnuPostSchedPost(reddit, sCommand[5:].strip(' ').lower())
    if sCommand.lower().startswith('edit '):
        sSub = sCommand[5:].strip(' ').lower()
        if IsValidSubLink(sSub, DB):
            return [Message(True,False,MessageType.Text,f"Para editar los posts recursivos hace click [Aqui](https://www.reddit.com/r/{sSub}/about/wiki/scheduledposts)")]
        return [Message(False,False,MessageType.Text,"Subreddit invalido")]
    else:
        return [Message(False,False,MessageType.Text,"schedposts list <Subreddit> - Muestra la lista de posts programados en el subreddit\nschedposts details <Subreddit> <ID(entero)> - Muestra los detalles del post programado\nschedposts post <Subreddit> <ID(entero)> - Postea un post programado\nschedposts edit <subreddit> - Muestra el link a la wiki en donde configurar los posts programados")]
async def GetSchedPostList(reddit, sSub):
    if IsValidSubLink(sSub, DB):
        schedPosts = await GetSchedPosts(reddit, sSub)
        sRetu = ""
        for schedpost in schedPosts.SchedPosts:
            sRetu = f"{sRetu}#{schedpost.Id} - {schedpost.Title}\r\n"
        return [Message(False,False,MessageType.Text,sRetu)]
    return [Message(False,False,MessageType.Text,"Subreddit invalido")]
async def GetSchedPosts(reddit, sSub):
        subreddit = await reddit.subreddit(sSub)
        wiki = await subreddit.wiki.get_page("scheduledposts")
        return GetSchedPostsFromWiki(wiki)
async def MnuPostSchedPost(reddit, sCommand):
    chunks = sCommand.split(' ')
    if IsValidSubLink(chunks[0], DB):
        if not chunks[1].isnumeric():
            return [Message(False,False,MessageType.Text,"Id Incorrecto")]
        iId = int(chunks[1])
        schedPosts = await GetSchedPosts(reddit, chunks[0])
        subreddit = await reddit.subreddit(chunks[0])
        Filtered = filter(lambda x: x.Id == iId, schedPosts.SchedPosts)
        Posted = False
        sRet = ""
        for Post in Filtered:
            Post.nextTime = "N/A"
            if await PostSchedPost(DB, reddit, subreddit, Post):
                RedditPostId = DB.GetDBValue(f"select PostID from ScheduledPosts where RedditID = {Post.Id} and Subreddit = '{chunks[0]}' order by PostedDate desc limit 1")
                sRet = f"{sRet}Post [{Post.Title}](https://www.reddit.com/r/{chunks[0]}/comments/{RedditPostId}/_/) Creado correctamente\n"
        if len(sRet) > 0:
            return [Message(True,True,MessageType.Text,sRet)]
        else:
            return [Message(False,False,MessageType.Text,"Hubo un error al crear el post, consulta los logs")] #PostSchedPost logs info
    return [Message(False,False,MessageType.Text,"Subreddit invalido")]
async def GetSchedPostDetails(reddit, sCommand):
    chunks = sCommand.split(' ')
    if IsValidSubLink(chunks[0], DB):
        if not chunks[1].isnumeric():
            return [Message(False,False,MessageType.Text,"Id Incorrecto")]
        iId = int(chunks[1])
        schedPosts = await GetSchedPosts(reddit,chunks[0])
        Filtered = filter(lambda x: x.Id == iId, schedPosts.SchedPosts)
        sRet = ""
        for Post in Filtered:
            sRet = f"{sRet}ID: {Post.Id}\nTitle: {Post.Title}\nBody: {Post.Body}\nFlair: {Post.Flair}\nSort By: {Post.Sort}\nRepeats every: "
            if Post.RepeatUnit.lower() == "custom":
                weekDayNames = ("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")
                weekdays = str(Post.RepeatValue).zfill(7)
                for i in range(0,7):
                    if weekdays[i] == "1":
                        sRet = f"{sRet}{weekDayNames[i]}, "
                sRet = sRet.strip(', ')
            else:
                sRet = f"{sRet}{Post.RepeatValue} {Post.RepeatUnit}"
            sRet = f"{sRet}\nStart Date: {Post.StartDate}\n"
            if Post.TimeLenght > 0:
                sRet = f"{sRet}Sticky for: {str(timedelta(seconds=Post.TimeLenght))}\nSticky Position: {Post.StickyPos}\n"
            else:
                sRet = f"{sRet}Sticky: No\n"
            if Post.EndsUnit.lower() == "never":
                sRet = f"{sRet}Recurrence ends: Never"
            elif Post.EndsUnit.lower() == "date":
                sRet = f"{sRet}Recurrence ends: {Post.EndsValue}"
            elif Post.EndsUnit.lower() == "occurrences":
                sRet = f"{sRet}Recurrence ends: After {Post.EndsValue} Occurrences"
        if len(sRet) > 0:
            return [Message(False,False,MessageType.Text,sRet)]
        else:
            return [Message(False,False,MessageType.Text,"Id Incorrecto")]
    return  [Message(False,False,MessageType.Text,"Subreddit invalido")]
async def HandleStats(sCommand, ModId, reddit):
    if sCommand.lower().startswith('mods'):
        return HandleModStats(sCommand[5:].strip(' '), ModId)
    if sCommand.lower().startswith('users'):
        return await HandleUserStats(sCommand[6:].strip(' '), reddit)
    if sCommand.lower().startswith('sub'):
        return HandleSubStats(sCommand[4:].strip(' '), ModId)
    else:
        return [Message(False,False,MessageType.Text,"stats mods (<mod name>)- Muestra estadisticas de los moderadores, puede filtrar por moderador individualmente\nstats users - Muestra estadisticas de los usuarios\nstats sub - Muestra estadisticas del subreddit")]
def SetPlotAsDates(filename):
    ax = plt.subplots()[1]
    fmt_day = mdates.DayLocator(interval = 5)
    ax.xaxis.set_major_locator(fmt_day)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
    ax.format_xdata = mdates.DateFormatter('%d/%m')
def CreateLinePlot(query,filename,xlabel, ylabel, title, new = True, lineLabel = '', fill= False, isXDateFormat = ''):
    rows = DB.ExecuteDB(query)
    Mes = []
    Cantidad = []
    if len(rows) > 0:
        if len(isXDateFormat)>0:
            rows = FillZeroesDateStatsArray(rows,isXDateFormat)
        for row in rows:
            Cantidad.append(row[0])
            if len(isXDateFormat)>0:
                Mes.append(datetime.strptime(row[1], isXDateFormat))
            else:
                Mes.append(row[1])
        if new:
            plt.clf()
        if len(lineLabel) > 0:
            plt.plot(Mes, Cantidad, label=lineLabel)
            plt.legend()
        else:
            plt.plot(Mes, Cantidad)
        if fill:
            plt.fill_between(Mes, Cantidad)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.title(title)
        plt.savefig(filename)
        return filename
    return ''
def FillZeroesDateStatsArray(rows, isXDateFormat):
    rRetu = []
    dLast = datetime.strptime(rows[len(rows)-1][1],isXDateFormat)
    dFirst = datetime.strptime(rows[0][1],isXDateFormat)
    Done = False
    while not Done:
        if dFirst == dLast:
            Done = True
        lFind = list(filter(lambda x: x[1] == dFirst.strftime(isXDateFormat),rows))
        if len(lFind) > 0:
            rRetu.append(lFind[0])
        else:
            rRetu.append((0, dFirst.strftime(isXDateFormat)))
        dFirst = dFirst + relativedelta(days=+1)
    return rRetu
def HandleModStats(sCommand, ModID):
    msgRetu = []
    if len(sCommand) > 0:
        sCommand = sCommand.lower()
        msgRetu.append(Message(False,False,MessageType.Text,f"**Estadisticas del mod {sCommand}**\n" + DB.GetTable(f"Select at.Description as Motivo, count(1) as Cantidad from Actions A join DiscordUsers M on M.Id = A.Mod join ActionType AT on A.ActionType = AT.Id Where lower(M.Name) = '{sCommand}' group by at.Description order by Cantidad desc")))
        plot = GetModYearLog(sCommand,'../img/plot.png')
        if len(plot) > 0:
            msgRetu.append(Message(False,False,MessageType.Image,plot))
        plot = GetModMonthLog(sCommand,'../img/plotm.png')
        if len(plot) > 0:
            msgRetu.append(Message(False,False,MessageType.Image,plot))
        plot = GetModHourLog(sCommand,'../img/ploth.png', ModID)
        if len(plot) > 0:
            msgRetu.append(Message(False,False,MessageType.Image,plot))
    else:
        msgRetu.append(Message(False,False,MessageType.Text,"**Estadisticas de Moderadores**\n" + DB.GetTable("select t1.Moderador, t1.Cantidad, t2.Puntos, printf(\"%.2f\", t2.Puntos*1.0 / t1.Cantidad*1.0) as PuntosPorAccion from  (select m.Name as Moderador, count(1) as Cantidad from Actions A join DiscordUsers M on M.Id = A.Mod group by m.Name) t1 join (select m.Name as Moderador, sum(AT.Weight) as Puntos from Actions A join ActionType AT on A.ActionType = AT.Id join DiscordUsers M on M.Id = A.Mod group by m.Name) t2 on t2.Moderador =t1.Moderador order by PuntosPorAccion desc") + "\n\n"))
    return msgRetu
def GetModYearLog(sCommand, pltName, lineLabel = '', new = True):
    sCommand = sCommand.lower().replace('_', '\_')
    sQuery =    "select sum(cnt) as cnt, mes From(" \
                "select count(1) as 'cnt', strftime(\"%Y-%m\", a.Date) as 'mes' "\
                "from Actions A "\
                "join DiscordUsers M on M.Id = A.Mod "\
                f"where lower(M.name) = '{sCommand}' "\
                "and a.Date > DATE(Date(),'-1 years') "\
                "group by mes "\
                "union "\
                "select count(1) as 'cnt', strftime(\"%Y-%m\", ML.Date) as 'mes' "\
                "from ModLog ML "\
                "join RedditUsers R on lower(R.redditname) = lower(ML.ModName) " \
                "join DiscordRedditUser DR on DR.RedditId =R.Id " \
                "join DiscordUsers M on M.Id = DR.DiscordId "\
                f"where lower(M.Name) = '{sCommand}' and ML.Date > DATE(Date(),'-1 years') "\
                "and (ML.Action like 'approve%' or ML.Action like 'remove%') "\
                "group by mes)H group by mes"
    if new == False:
        return CreateLinePlot(sQuery,pltName, 'Mes', 'Cantidad de Acciones', 'Acciones por Mes', new, lineLabel)
    CreateLinePlot(sQuery,pltName, 'Mes', 'Cantidad de Acciones', 'Acciones por Mes', new,lineLabel = "Aprobados",fill = True)
    sQuery =    "select sum(cnt) as cnt, mes From(" \
                "select count(1) as 'cnt', strftime(\"%Y-%m\", a.Date) as 'mes' "\
                "from Actions A "\
                "join DiscordUsers M on M.Id = A.Mod "\
                f"where lower(M.name) = '{sCommand}' "\
                "and a.Date > DATE(Date(),'-1 years') "\
                "group by mes "\
                "union "\
                "select count(1) as 'cnt', strftime(\"%Y-%m\", ML.Date) as 'mes' "\
                "from ModLog ML "\
                "join RedditUsers R on lower(R.redditname) = lower(ML.ModName) " \
                "join DiscordRedditUser DR on DR.RedditId =R.Id " \
                "join DiscordUsers M on M.Id = DR.DiscordId "\
                f"where lower(M.Name) = '{sCommand}' and ML.Date > DATE(Date(),'-1 years') "\
                "and (ML.Action like 'remove%') "\
                "group by mes)H group by mes"
    return CreateLinePlot(sQuery,pltName, 'Mes', 'Cantidad de Acciones', 'Acciones por Mes', False, lineLabel = "Removidos",fill = True)
def GetModMonthLog(sCommand, pltName, lineLabel = '', new = True):
    fig, ax = plt.subplots()
    fmt_day = mdates.DayLocator(interval = 5)
    ax.xaxis.set_major_locator(fmt_day)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
    sCommand = sCommand.lower().replace('_', '\_')
    sQuery =    "select sum(cnt) as cnt, dia From(" \
                "select count(1) as 'cnt', strftime(\"%Y-%m-%d\", a.Date) as 'dia' "\
                "from Actions A "\
                "join DiscordUsers M on M.Id = A.Mod "\
                f"where lower(M.name) = '{sCommand}' "\
                "and a.Date > DATE(Date(),'-1 months') "\
                "group by dia "\
                "union "\
                "select count(1) as 'cnt', strftime(\"%Y-%m-%d\", ML.Date) as 'dia' "\
                "from ModLog ML "\
                "join RedditUsers R on lower(R.redditname) = lower(ML.ModName) " \
                "join DiscordRedditUser DR on DR.RedditId =R.Id " \
                "join DiscordUsers M on M.Id = DR.DiscordId "\
                f"where lower(M.Name) = '{sCommand}' and ML.Date > DATE(Date(),'-1 months') "\
                "and (ML.Action like 'approve%' or ML.Action like 'remove%') "\
                "group by dia)H group by dia order by dia"
    if new == False:
        return CreateLinePlot(sQuery,pltName, 'Dia', 'Cantidad de Acciones', 'Acciones por Dia', new, lineLabel,isXDateFormat="%Y-%m-%d")
    CreateLinePlot(sQuery,pltName, 'Dia', 'Cantidad de Acciones', 'Acciones por Dia', new,lineLabel = "Aprobados",fill = True,isXDateFormat="%Y-%m-%d")
    sQuery =    "select sum(cnt) as cnt, dia From(" \
                "select count(1) as 'cnt', strftime(\"%Y-%m-%d\", a.Date) as 'dia' "\
                "from Actions A "\
                "join DiscordUsers M on M.Id = A.Mod "\
                f"where lower(M.name) = '{sCommand}' "\
                "and a.Date > DATE(Date(),'-1 months') "\
                "group by dia "\
                "union "\
                "select count(1) as 'cnt', strftime(\"%Y-%m-%d\", ML.Date) as 'dia' "\
                "from ModLog ML "\
                "join RedditUsers R on lower(R.redditname) = lower(ML.ModName) " \
                "join DiscordRedditUser DR on DR.RedditId =R.Id " \
                "join DiscordUsers M on M.Id = DR.DiscordId "\
                f"where lower(M.Name) = '{sCommand}' and ML.Date > DATE(Date(),'-1 months') "\
                "and (ML.Action like 'remove%') "\
                "group by dia)H group by dia order by dia"
    sRet = CreateLinePlot(sQuery,pltName, 'Dia', 'Cantidad de Acciones', 'Acciones por Dia', False, lineLabel = "Removidos",fill = True,isXDateFormat="%Y-%m-%d")
    ax.format_xdata = mdates.DateFormatter('%d/%m')
    fig.autofmt_xdate()
    plt.savefig(pltName)
    return sRet
def GetModHourLog(sCommand, pltName, ModId, lineLabel = '', new = True):
    sCommand = sCommand.lower().replace('_', '\_')
    sQuery = "select ifnull(counts.Cantidad,0) , cnt.x  "\
            "from   "\
            "( "\
            "	WITH RECURSIVE cnt(x) AS  "\
            "	(SELECT 0 UNION ALL SELECT x+1  "\
            "	FROM cnt LIMIT 24)  "\
            "	SELECT x FROM cnt "\
            ") as cnt  "\
            "left join   "\
            "(select sum(Cantidad) as Cantidad, Hora From( "\
            f"	select count(1) as Cantidad,cast(strftime(\"%H\", DATETIME(DATETIME(a.Date,'-'||(select Value from Settings where [Key]= 'HusoHorarioDB')||' hours' ), (select TimeZone from DiscordUsers where Id = {ModId})|| ' hours')) as INTEGER) as Hora  "\
            "	from Actions A  "\
            "	join DiscordUsers M on M.Id = A.Mod  "\
            f"	where lower(M.name) = '{sCommand}' and a.Date > DATE(Date(),'-1 years')  "\
            "	group by Hora "\
            "	union  "\
            "	select count(1) as Cantidad,  "\
            "	cast(strftime(\"%H\", DATETIME(ML.Date, (select TimeZone from DiscordUsers where Id = 1)|| ' hours')) as INTEGER) as Hora  "\
            "	from ModLog ML "\
            "join RedditUsers R on lower(R.redditname) = lower(ML.ModName) " \
            "join DiscordRedditUser DR on DR.RedditId =R.Id " \
            "join DiscordUsers M on M.Id = DR.DiscordId "\
            f"	where lower(M.Name) = '{sCommand}' and ML.Date > DATE(Date(),'-1 years')  "\
            "	and (ML.Action like 'approve%' or ML.Action like 'remove%') "\
            "	group by Hora) H group by Hora "\
            ") counts on counts.Hora = cnt.x"
    
    return CreateLinePlot(sQuery,pltName, 'Hora', 'Cantidad de Acciones', 'Acciones por Hora', new,lineLabel)
        #cantidad de acciones por mod
        #suma de pesos de acciones por mod
        # Horas de actividad
        #<Modname> Stats del mod
            #horas de actividad
            #dias de la semana
            #cantidad por dia (grafico?)
async def HandleUserStats(sCommand, reddit):
    #top users con mas medidas
    #top users con mas peso
    #porcentaje de users que responde a modmail
    if len(sCommand) > 0:
        return await HandleIndUserStats(reddit, sCommand)
    Limite = 20
    if check_int(sCommand):
        Limite = int(sCommand)
    sRetu = [Message(False,False,MessageType.Text,f"**Top {str(Limite)} usuarios con mas acciones**\n" + DB.GetTable(f"select R.RedditName, count(1) as Cantidad from Actions A join RedditUsers R on R.Id = A.RedditUserId group by R.RedditName order by Cantidad desc LIMIT {Limite}"))]
    sRetu.append(Message(False,False,MessageType.Text, f"**Cantidad de usuarios por cantidad de acciones**\n" + DB.GetTable(f"Select Cantidad as CantidadDeFaltas, count(RedditUserId) as Usuarios from (select A.RedditUserId, count(1) as cantidad from Actions A join ActionType AT on AT.Id = A.ActionType where AT.Weight > 0 group by A.RedditUserId) as Users group by Cantidad")))
    return sRetu
async def HandleIndUserStats(reddit, sCommand):
    oUser = await reddit.redditor(sCommand)
    sSubreddits = DB.GetSetting("subreddit") #checked
    await oUser.load()
    MsgsRetu = GetWarns(sCommand, True)
    for sSubreddit in sSubreddits:
        MsgsRetu.append(await indUserStatsSub(reddit, sCommand, sSubreddit, oUser))
    return MsgsRetu
async def indUserStatsSub(reddit, sCommand, sSubreddit, oUser):
    submissions = []
    async for comment in oUser.comments.new(limit=None):
        if comment.subreddit_name_prefixed == "r/" + sSubreddit:
            submissions.append(UserSubmission("comment",comment.created_utc, comment.score, comment.removed))
    async for post in oUser.submissions.new(limit=None):
        if post.subreddit_name_prefixed == "r/" + sSubreddit:
            submissions.append(UserSubmission("post",post.created_utc, post.score, post.removed))
    if len(submissions) == 0:
        return Message(False,False,MessageType.Text,f"El usuario {sCommand} no participa del subrredit r/{sSubreddit}")
    AccountCreated = datetime.fromtimestamp(oUser.created_utc)
    FirstDateOfParticipation = datetime.fromtimestamp(min(submissions,key = lambda post: post.Created).Created)
    CommentKarma = sum(p.score for p in filter(lambda x: x.Type == "comment", submissions))
    CommentCount = len(list(filter(lambda x: x.Type == "comment", submissions)))
    if CommentCount > 0:
        CommentPercRemoved = (len(list(filter(lambda x: x.Type == "comment" and x.removed, submissions)))/CommentCount)*100
    else:
        CommentPercRemoved = 0
    PostKarma = sum(p.score for p in filter(lambda x: x.Type == "post", submissions))
    PostCount = len(list(filter(lambda x: x.Type == "post", submissions)))
    if PostCount > 0:
        PostPercRemoved = (len(list(filter(lambda x: x.Type == "post" and x.removed, submissions)))/PostCount)*100
    else:
        PostPercRemoved = 0
    daysActive = (datetime.today() - FirstDateOfParticipation).days
    subsPerDay = len(submissions) / daysActive 
    return Message(True,False,MessageType.Text,\
        f"**r/{sSubreddit}**\n****Cuenta Creada:** {AccountCreated.strftime('%Y-%m-%d')}\n**Participa en el sub desde:** {FirstDateOfParticipation.strftime('%Y-%m-%d')}\n"\
        f"**Comentarios**\n---**Cantidad:** {CommentCount}\n---**Karma: **{CommentKarma}\n---**Porcentaje de removidos:** {'{0:.3g}'.format(CommentPercRemoved)}%\n"\
        f"**Posts**\n---**Cantidad:** {PostCount}\n---**Karma: **{PostKarma}\n---**Porcentaje de removidos:** {'{0:.3g}'.format(PostPercRemoved)}%\n"\
        f"**Submissiones promedio por dia:** {'{0:.3g}'.format(subsPerDay)}")
def GetActingMods(TimeBack):
    sQuery = "select Name from( " \
            "select M.Name, min(A.Date) as Date " \
            "from Actions A " \
            "join DiscordUsers M on M.ID = a.Mod " \
            f"where datetime(a.Date) >=datetime('now', '{TimeBack}') " \
            "group by M.Name " \
            "UNION " \
            "select D.Name, min(Date) as Date " \
            "from ModLog ML " \
            "join RedditUsers R on r.RedditName = ML.ModName " \
            "join DiscordRedditUser DR on DR.RedditId = R.Id " \
            "join DiscordUsers D on D.ID = DR.DiscordId " \
            f"where datetime(Date) >=datetime('now', '{TimeBack}') " \
            "and (action like 'approve%' or action like 'remove%') " \
            "group by D.Name)A group by Name order by min(Date)"
    return DB.ExecuteDB(sQuery)

def HandleSubStats(sCommand, ModId):
    sRetu = [Message(False,False,MessageType.Text,f"**Modmail**\n" + DB.GetTable(f"select a1.Enviados, a2.Respondidos, printf(\"%.2f\",(100.00*a2.Respondidos)/a1.Enviados) as PorcentajeRespondidos from (select count(distinct ActionId) as Enviados,'a' as a from Modmails) a1 join (select count(distinct ActionId) as Respondidos ,'a' as a from Modmails where lastmodmailupdated is not null) a2 on a1.a = a2.a"))]
    sRetu.append(Message(False,False,MessageType.Text, f"**Cantidad de Acciones tomadas**\n" + DB.GetTable(f"select AT.Description as Descripcion, count(1) as Cantidad from Actions A join ActionType AT on AT.Id = A.ActionType group by AT.Description order by Cantidad desc")))
    #sRetu.append(Message(False,False,MessageType.Text, f"**Acciones por dia de la semana**\n" + DB.GetTable("select case DDW when '0' then 'Domingo' when '1' then 'Lunes' when '2' then 'Martes' when '3' then 'Miercoles' when '4' then 'Jueves' when '5' then 'Viernes' when '6' then 'Sabado' end as DiaDeLaSemana, Cantidad from (SELECT strftime('%w',Date) DDW, count(1) as Cantidad from actions group by DDW)") + "\n"))

    plot = CreateLinePlot(f"select count(1) as 'cnt', strftime(\"%Y-%m\", a.Date) as 'mes' from Actions A where a.Date > DATE(Date(),'-1 years') group by strftime(\"%Y-%m\", a.Date)",'../img/plot.png', 'Mes', 'Cantidad de Medidas', 'Medidas por Mes')
    if len(plot) > 0:
        sRetu.append(Message(False,False,MessageType.Image,plot))

    plot = CreateLinePlot(f"select count(1) as 'cnt', strftime(\"%Y-%m\", a.Date) as 'mes' from Actions A join ActionType AT on AT.Id = A.ActionType where AT.Weight > 0 and a.Date > DATE(Date(),'-1 years') group by strftime(\"%Y-%m\", a.Date)",'../img/plotp.png', 'Mes', 'Cantidad de Medidas', 'Medidas punitivas por Mes')
    if len(plot) > 0:
        sRetu.append(Message(False,False,MessageType.Image,plot))

    rows = GetActingMods('-1 years')
    plt.clf()
    for row in rows:
        plot = GetModYearLog(row[0],'../img/ploty.png',row[0], False)
    if len(plot) > 0:
        sRetu.append(Message(False,False,MessageType.Image,plot))

    sQuery = "select ifnull(counts.Cantidad,0) , cnt.x  "\
            "from   "\
            "	(WITH RECURSIVE cnt(x) AS  "\
            "	(SELECT 0  "\
            "	UNION ALL  "\
            "	SELECT x+1  "\
            "	FROM cnt LIMIT 24)  "\
            "	SELECT x FROM cnt) as cnt  "\
            "left join   "\
            "	(select sum(Cantidad) as Cantidad, Hora From "\
            "		(select count(1) as Cantidad, "\
            f"		cast(strftime(\"%H\", DATETIME(DATETIME(a.Date,'-'||(select Value from Settings where [Key]= 'HusoHorarioDB')||' hours' ), (select TimeZone from DiscordUsers where Id = {ModId})|| ' hours')) as INTEGER) as Hora  "\
            "		from Actions A "\
            "		Join DiscordUsers M on M.Id = A.Mod  Join UserRoles UR on UR.DiscordId = M.Id join Roles R on R.Id = UR.RoleId "\
            "		where R.Name = 'Reddit Mod' group by Hora "\
            "		union  "\
            "		select count(1) as Cantidad,  "\
            f"		cast(strftime(\"%H\", DATETIME(DATETIME(ML.Date,'-'||(select Value from Settings where [Key]= 'HusoHorarioDB')||' hours' ), (select TimeZone from DiscordUsers where Id = {ModId})|| ' hours')) as INTEGER) as Hora  "\
            "		from ModLog ML "\
            "		Where ML.Date > DATE(Date(),'-1 years')  "\
            "		and (ML.Action like 'approve%' or ML.Action like 'remove%') "\
            "		group by Hora "\
            "		)group by Hora) counts on counts.Hora = cnt.x"
    plot = CreateLinePlot(sQuery,'../img/ploth.png', 'Mes', 'Cantidad de Acciones', 'Acciones por Hora')
    if len(plot) > 0:
        sRetu.append(Message(False,False,MessageType.Image,plot))
    
    plt.clf()
    rows = GetActingMods('-1 years')
    for row in rows:
        plot = GetModHourLog(row[0],'../img/plotm.png', ModId,row[0], False)
    if len(plot) > 0:
        sRetu.append(Message(False,False,MessageType.Image,plot))
    
    return sRetu
def HandlePolicies(sCommand, UserRoles):
    if sCommand.lower().startswith('list'):
        return GetPolicies()
    if sCommand.lower().startswith('edit '):
        if 'Bot Config' in UserRoles: 
            return EditPol(sCommand[4:].strip(' '))
        else:
            return [Message(False,False,MessageType.Text,"Se requiere del rol Bot Config para modificar politicas.")]
    if sCommand.lower().startswith('remove '):
        if 'Bot Config' in UserRoles: 
            return RemovePol(sCommand[7:].strip(' '))
        else:
            return [Message(False,False,MessageType.Text,"Se requiere del rol Bot Config para eliminar politicas.")]
    else:
        return [Message(False,False,MessageType.Text,"policies list - Muestra un listado de las politicas de moderacion\npolicies remove <id> - Elimina una politica de moderacion\npolicies edit <id(entero, si esta vacio es un nuevo registro)>,<From(entero)>,<To(entero)>,<Action(warn/ban)>,<BanDays(entero, si esta vacio es permanente)>,<Message(modmail)> - Agrega o edita una politica de moderacion")]
def EditPol(sCommand):
    sParams = sCommand.split(',')
    if len(sParams) >= 6:
        sMessage = sCommand[len(sParams[0])+len(sParams[1])+len(sParams[2])+len(sParams[3])+len(sParams[4]) +5:].strip(' ')
        if (len(sParams[0].strip(' ')) == 0 or check_int(sParams[0].strip(' '))) and check_int(sParams[1].strip(' ')) and check_int(sParams[2].strip(' ')) and (sParams[3].strip(' ').lower() == "warn" or sParams[3].strip(' ').lower() == "ban") and (len(sParams[4].strip(' ')) == 0 or check_int(sParams[4].strip(' '))) and len(sMessage.strip(' ')) > 0:
            banDays = sParams[4].strip(' ')
            if len(banDays) == 0:
                banDays = "-1"
            if sParams[3].strip(' ').lower() == "warn":
                sAction = 1
            else:
                sAction = 2
            row = (sParams[1],sParams[2],sAction,banDays,sMessage)
            if len(sParams[0].strip(' ')) == 0: #Agregar politica
                DB.WriteDB(f"""INSERT INTO Policies ([From], [To], Action, BanDays, Message) VALUES (?,?,?,?,?);""",row)
                return [Message(False,False,MessageType.Text,"Politica agregada")]
            else: # Editar politica
                rows = DB.ExecuteDB(f"SELECT * FROM Policies where Id = {sParams[0].strip(' ')}")
                if len(rows) > 0:
                    DB.WriteDB(f"Update Policies set [From] = ?, [To] = ?, Action = ?, BanDays = ?, Message = ? WHERE Id = {sParams[0].strip(' ')}", row)
                    return [Message(False,False,MessageType.Text,f"Politica #{sParams[0].strip(' ')} actualizada.")]
                return [Message(False,False,MessageType.Text,f"Politica #{sParams[0].strip(' ')} no encontrada.")]
    return [Message(False,False,MessageType.Text,"Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\n<id(entero, si esta vacio es un nuevo registro)>,<From(entero)>,<To(entero)>,<Action(warn/ban)>,<BanDays(entero, si esta vacio es permanente)>,<Message(modmail)>\n\nReferencias a tener en cuenta al confeccionar el Mod Mail:\n[Sub] -> Nombre del subreddit a moderar\n[Link] -> Link sancionado\n[ActionTypeDesc] -> Por que fue sancionado el link\n[Details] -> Notas del moderador\n[Summary] -> Resumen de faltas\n\\n -> Nueva linea")]

def RemovePol(sId):
    if not check_int(sId):
        return [Message(False,False,MessageType.Text,"Id Incorrecto")]
    iId = int(sId)
    rows = DB.ExecuteDB(f"SELECT * FROM Policies where Id = {iId}")
    if len(rows) > 0:
        DB.WriteDB(f"DELETE FROM Policies WHERE Id = {iId}")
        return [Message(False,False,MessageType.Text,f"Politica #{iId} eliminada.")]
    return [Message(False,False,MessageType.Text,f"Politica #{iId} no encontrada.")]
def GetPolicies():
    rows = DB.ExecuteDB(f"SELECT * FROM Policies")
    sRetu = ""
    for row in rows:
        sRetu = sRetu + f"Id: {row[0]}\nFrom: {row[1]}\nTo: {row[2]}\nAction: "
        if row[3] == 1:
            sRetu = sRetu + "Warn"
        else:
            sRetu = sRetu + "Ban: "
            if row[4] < 1:
                sRetu = sRetu + "Permanente"
            else:
                sRetu = sRetu + f"{row[4]} Dias"
        sRetu = sRetu + f"\nMod Mail: {row[5]}\n--------------------\n"
    return [Message(False,False,MessageType.Text,sRetu)]
def GetLinkType(sIn):
    sIn = SanatizeRedditLink(sIn)
    chunks = sIn.split('/')
    if len(chunks) == 0:
        return 0 #invalid link
    if chunks[0].startswith('mod.reddit.com'):
        return 3 #Modmail
    if len(chunks) == 6:
        return 1 #link/post
    if len(chunks) == 7:
        return 2 #comment
    return 0 
async def Unban(sUser, reddit):
    subs = DB.GetSetting("subreddit") #checked
    for sSub in subs:
        sub = await reddit.subreddit(sSub)
        await sub.banned.remove(sUser)
    return [Message(False,False,MessageType.Text,f"Usuario {sUser} ha sido desbanneado.")]
async def ApproveUser(sUser, reddit):
    subs = DB.GetSetting("subreddit") #checked
    for sSub in subs:
        sub = await reddit.subreddit(sSub)
        await sub.contributor.add(sUser)
    return [Message(False,False,MessageType.Text,f"Usuario {sUser} ha sido agregado a users aprobados.")]
def HandleUsers(sCommand, UserRoles):
    if sCommand.lower().startswith('list'):
        return GetUsers()
    elif sCommand.lower().startswith('search '):
        return SearchUser(sCommand[7:].strip(' '))
    elif sCommand.lower().startswith('addrole '):
        if 'Bot Config' in UserRoles or 'Admin' in UserRoles: 
            return AddRole(sCommand[8:].strip(' '),UserRoles)
        else:
            return [Message(False,False,MessageType.Text,"Se requiere del rol Bot Config para agregar roles a usuarios.")]
    if sCommand.lower().startswith('removerole '):
        if 'Bot Config' in UserRoles or 'Admin' in UserRoles: 
            return RemoveRole(sCommand[11:].strip(' '),UserRoles)
        else:
            return [Message(False,False,MessageType.Text,"Se requiere del rol Bot Config para remover roles de usuarios.")]
    if sCommand.lower().startswith('details '):
        return GetUserDetails(sCommand[8:].strip(' '))
    else:
        return [Message(False,False,MessageType.Text,"users list - Muestra un listado de los usuarios autorizados para usar el bot\nusers search <Usuario> - Busca usuarios entre todos los usuarios registrados\nusers details <Usuario> - Muestra los detalles del usuario\nusers addrole <Usuario> <Rol> - Agrega un rol a un usuario\nusers removerole <Usuario> <Rol> - Remueve un rol a un usuario")]
def HandleSettings(sCommand, UserRoles):
    if sCommand.lower().startswith('list'):
        return GetSettings()
    if sCommand.lower().startswith('edit '):
        if 'Bot Config' in UserRoles: 
            return EditSetting(sCommand[5:].strip(' '))
        else:
            return [Message(False,False,MessageType.Text,"Se requiere del rol Bot Config para editar las preferencias del bot.")]
    else:
        return [Message(False,False,MessageType.Text,"settings list - Muestra un listado de preferencias\nsettings edit <setting> <value> - Edita una preferencia")]
def HandleRoles(sCommand):
    return GetRoles()
def EditSetting(sCommand):
    chunks = sCommand.split(' ')
    if len(chunks) < 2:
        return [Message(False,False,MessageType.Text,"Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\nsettings edit <setting> <value>")]
    rows = DB.ExecuteDB(f"SELECT * FROM Settings where [Key] = '{chunks[0].strip(' ')}'")
    if len(rows) == 0:
        return [Message(False,False,MessageType.Text,"Preferencia no encontrada")]
    sValue = sCommand[len(chunks[0]):].strip(' ')
    if rows[0][3] == "int":
        if not check_int(sValue):
            return [Message(False,False,MessageType.Text,f"La preferencia {chunks[0]} debe ser un numero entero")]
    DB.WriteDB(f"UPDATE Settings SET [Value] = '{sValue}' WHERE Id = {rows[0][0]};")
    return [Message(False,False,MessageType.Text,f"La preferencia {chunks[0]} ha sido actualizada")]
def AddRole(sCommand,UserRoles):
    chunks = sCommand.lower().split(' ')
    sRole = sCommand[len(chunks[0]):].strip(' ').lower()
    if sRole == 'Admin' and 'Admin' not in UserRoles:
        return [Message(False,False,MessageType.Text,"Se requiere del rol Admin para agregar este rol.")]
    if len(chunks) < 2:
        return [Message(False,False,MessageType.Text,"Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\nusers addrole <User> <Role>")]
    sUser = chunks[0].strip(' ').lower()
    if sUser.startswith("<@!") and sUser.endswith(">"):
        UserId = DB.GetDBValue(f"SELECT Id FROM DiscordUsers where DiscordId = {sUser[3:-1]}")
    else:
        UserId = DB.GetDBValue(f"SELECT Id FROM DiscordUsers where lower(Name) = '{sUser}'")
    if UserId is None:
        return [Message(False,False,MessageType.Text,"Usuario no encontrado")]
    RoleId = DB.GetDBValue(f"SELECT Id FROM Roles where lower(Name) = '{sRole}'")
    if RoleId is None:
        return [Message(False,False,MessageType.Text,"Rol no encontrado")]
    URId = DB.GetDBValue(f"SELECT Id FROM UserRoles where DiscordId = {UserId} and RoleId = {RoleId}")
    if URId is not None:
        return [Message(False,False,MessageType.Text,"El usuario ya tiene ese rol")]
    DB.WriteDB(f"Insert into UserRoles(DiscordId, RoleId) values ({UserId},{RoleId});")
    return [Message(False,False,MessageType.Text,f"El usuario {sUser} ha sido agregado al rol {sRole}")]
def check_int(s):
    if s is not None and len(str(s)) > 0:
        if str(s)[0] in ('-', '+'):
            return str(s)[1:].isdigit()
        return str(s).isdigit()
    return 0
def RemoveRole(sCommand,UserRoles):
    chunks = sCommand.lower().split(' ')
    sRole = sCommand[len(chunks[0]):].strip(' ').lower()
    if sRole == 'Admin' and 'Admin' not in UserRoles:
        return [Message(False,False,MessageType.Text,"Se requiere del rol Admin para quitar este rol.")]
    if len(chunks) < 2:
        return [Message(False,False,MessageType.Text,"Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\nusers removerole <User> <Role>")]
    sUser = chunks[0].strip(' ').lower()
    if sUser.startswith("<@!") and sUser.endswith(">"):
        UserId = DB.GetDBValue(f"SELECT Id FROM DiscordUsers where DiscordId = {sUser[3:-1]}")
    else:
        UserId = DB.GetDBValue(f"SELECT Id FROM DiscordUsers where lower(Name) = '{sUser}'")
    if UserId is None:
        return [Message(False,False,MessageType.Text,"Usuario no encontrado")]
    RoleId = DB.GetDBValue(f"SELECT Id FROM Roles where lower(Name) = '{sRole}'")
    if RoleId is None:
        return [Message(False,False,MessageType.Text,"Rol no encontrado")]
    URId = DB.GetDBValue(f"SELECT Id FROM UserRoles where DiscordId = {UserId} and RoleId = {RoleId}")
    if URId is None:
        return [Message(False,False,MessageType.Text,"El usuario no pertenece a ese rol")]
    DB.WriteDB(f"DELETE FROM UserRoles WHERE Id = {URId}")
    return [Message(False,False,MessageType.Text,f"El usuario {sUser} ha sido removido del rol {sRole}")]
def GetUserDetails(sCommand):
    DiscordUsers = DB.ExecuteDB(f"Select D.* from DiscordUsers D Join UserRoles UR on UR.DiscordId = D.Id Join Roles RL on RL.Id = UR.RoleId where lower(D.Name) = '{sCommand.lower().strip(' ')}' and RL.Name = 'Bot User'")
    if len(DiscordUsers) > 0:
        DiscordUser = DiscordUsers[0]
        sRetu = f"**{DiscordUser[1]}**\nDiscord Id: {DiscordUser[2]}\nTime Zone: {DiscordUser[3]}\nRoles:\n"
        Roles = DB.ExecuteDB("select R.Name " \
                    "from UserRoles UR " \
                    "join DiscordUsers D on D.Id = UR.DiscordId " \
                    "join Roles R on R.Id = UR.RoleId " \
                    f"where D.Id = {DiscordUser[0]} ")
        for Role in Roles:
            sRetu = f"{sRetu}\t{Role[0]}\n"
        RedditUsers = DB.ExecuteDB("Select R.* " \
	                                "from DiscordRedditUser DR " \
	                                "Join RedditUsers R on R.Id = DR.RedditId "\
	                                f"where DR.DiscordId = {DiscordUser[0]}")
        sRetu = f"{sRetu}Linked Reddit Users:\n"
        for RedditUser in RedditUsers:
            sRetu = f"{sRetu}\tUser: {RedditUser[1]}\n\tCake Day: {RedditUser[2]}\n"
        return [Message(False,False,MessageType.Text,sRetu)]
    return [Message(False,False,MessageType.Text,f"Usuario no encontrado")]
def GetUsers():
    return [Message(False,False,MessageType.Text,DB.GetTable("Select D.Name, D.DiscordId, R.RedditName " \
                                                            "from DiscordUsers D " \
                                                            "Join UserRoles UR on UR.DiscordId = D.Id " \
                                                            "Join Roles RL on RL.Id = UR.RoleId " \
                                                            "left join DiscordRedditUser DR on DR.DiscordId = D.Id " \
                                                            "left join RedditUsers R on R.Id = DR.RedditId " \
                                                            "Where RL.Name = 'Bot User'"))]
def SearchUser(sIn):
    sUser = sIn.strip(' ').lower()
    return [Message(False,False,MessageType.Text,DB.GetTable("Select D.Name, D.DiscordId, R.RedditName " \
                                                            "from DiscordUsers D " \
                                                            "left join DiscordRedditUser DR on DR.DiscordId = D.Id " \
                                                            "left join RedditUsers R on R.Id = DR.RedditId " \
                                                            f"Where lower(D.Name) like '%{sUser}%' or lower(R.RedditName) like '%{sUser}%'"))]
def GetSettings():
    rows = DB.ExecuteDB(f"SELECT * FROM Settings")
    sRetu = ""
    for row in rows:
        sRetu = sRetu + f"Setting: {row[1]}\nValue: {row[2]}\n--------------------\n"
    return [Message(False,False,MessageType.Text,sRetu)]

def GetRoles():
    rows = DB.ExecuteDB(f"SELECT * FROM Roles")
    sRetu = ""
    for row in rows:
        sRetu = sRetu + f"Id: {row[0]}\nRole: {row[1]}\n--------------------\n"
    return [Message(False,False,MessageType.Text,sRetu)]

def Unwarn(sId, Roles):
    if not sId.isnumeric():
        return [Message(False,False,MessageType.Text,"Id Incorrecto")]
    iId = int(sId)
    WarnType = GetWarnType(iId)
    if WarnType is not None:
        if 'Reddit Mod' in Roles or ('Discord Mod' in Roles and WarnType == "Discord"): 
            return [Message(False,False,MessageType.Text,ConfirmedUnwarn(DB,iId))]
        else:
            return [Message(False,False,MessageType.Text,"Se requiere del rol Reddit Mod para remover warns de reddit.")]
    return [Message(False,False,MessageType.Text,f"Warn #{iId} no encontrado.")]
def GetWarnType(iId):
    return DB.GetDBValue(f"select case when DiscordUserId is null then 'Reddit' else 'Discord' end from Actions where Id = {iId}")
def GetWarns(sUser, summary = False):
    rows = GetCommonActionDetails(DB, "RedditName",sUser,False)
    sRetu = f"**Warns del usuario {sUser}**\n"
    dateFrom = datetime.now() - timedelta(days=int(DB.GetSetting("warnexpires")))
    iWeight = 0
    for row in rows:
        if datetime.strptime(row['Date'], '%Y-%m-%d %H:%M:%S.%f') >= dateFrom:
            sActive = "Si"
            if not row['Weight'] is None:
                iWeight = iWeight + row['Weight']
        else:
            sActive = "No"
        if summary:
            sRetu += f"[{row['TypeDesc']}](https://{row['Link']}) - Puntos: {row['Weight']}\n"
        else:
            sRetu += f"Warn Id: {row['Id']} \nMod: {row['ModName']} \nFecha: {row['Date']}\nActivo: {sActive}\n[{row['TypeDesc']}](https://{row['Link']})\nPuntos: {row['Weight']}\nDetalles: {row['Details']}\n"
            if row['Snapshot'] is not None and len(row['Snapshot']) > 0:
                sRetu = f"{sRetu}Snapshot:\n{row['Snapshot']}\n"
            sRetu += "--------------------\n"
    if len(sRetu) == 0:
        sRetu = f"No se encontaron warns para el usuario {sUser}"
    else:
        sRetu += f"Total: {iWeight} Puntos"
    return [Message(True,False,MessageType.Text,sRetu)]
def CheckSender(author):
    mRoles = DB.ExecuteDB("select R.Name " \
                        "from UserRoles UR " \
                        "join DiscordUsers D on D.Id = UR.DiscordId " \
                        "join Roles R on R.Id = UR.RoleId " \
                        f"where D.DiscordId = {author.id} ")
    Roles = []
    for Role in mRoles:
        Roles.append(Role[0])
    Id = DB.GetDBValue(f"select Id from DiscordUsers where DiscordId = {author.id}")
    PendingAction = None
    if Id is not None:
        PendingAction = DB.GetDBValue(f"SELECT Id FROM Actions WHERE Mod = {Id} and ActionType is null and Processing is null and RedditUserId is not null")
    return UserStatus(Id, Roles, PendingAction)

def GetActionTypes(UserName, filter = "", FormatTable = False):
    sRetu = ""
    Weight = GetUsersCurrentWeight(UserName)
    sQuery = f"SELECT '!' || t.Id as Id, t.Description as Descripcion, case t.Weight when 0 then 'Advertencia' else case p.Action when 1 then 'Advertencia' when 2 then case p.BanDays when -1 then 'Ban Permanente' else 'Ban ' || p.BanDays || ' Dias' End End End as Accion, t.Weight as Puntos FROM ActionType t join Policies p on p.[From] <= t.Weight + {Weight} and p.[To] >= t.Weight + {Weight} Where t.Active = 1 and t.Description like '%{filter}%' order by trim(t.Description), t.Weight desc"
    if FormatTable:
        return DB.GetTable(sQuery)
    rows = DB.ExecuteDB(sQuery)
    for row in rows:
        sRetu = f"{sRetu}{row[0]} - {row[1]} - **Puntos:** {row[3]} - **Accion: {row[2]} **\n"
    return sRetu

def GetUsersCurrentWeight(sUser):
    dateFrom = datetime.now() - timedelta(days=int(DB.GetSetting("warnexpires")))
    sQuery = 	"select sum(Weight) as Weight from( " \
	            "Select ifnull(Sum(t.Weight),0) as Weight " \
	            "FROM Actions a  " \
	            "Join ActionType t on t.Id = a.ActionType  " \
	            "join DiscordRedditUser DRU on DRU.DiscordId = A.DiscordUserId " \
	            "join RedditUsers R on R.Id = DRU.RedditId " \
	            f"where lower(R.RedditName) = '{sUser.lower()}' " \
	            f"and a.Date >= '{dateFrom}' " \
	            "union " \
	            "Select ifnull(Sum(t.Weight),0) as Weight " \
	            "FROM Actions a  " \
	            "Join ActionType t on t.Id = a.ActionType  " \
	            "join RedditUsers R on R.Id = A.RedditUserId " \
	            f"where lower(R.RedditName) = '{sUser.lower()}' " \
	            f"and a.Date >= '{dateFrom}')  "
    rows = DB.ExecuteDB(sQuery)
    if(len(rows)) > 0 and check_int(rows[0][0]):
        return int(rows[0][0])
    return 0
def GetApplyingPolicy(ActionId, AddedWeight):
    rows = DB.ExecuteDB(f"Select R.RedditName FROM Actions A join RedditUsers R on R.Id = A.RedditUserId WHERE A.Id = {ActionId}")
    if len(rows) > 0:
        if AddedWeight > 0:
            Weight = GetUsersCurrentWeight(rows[0][0]) + AddedWeight
        else:
            Weight = AddedWeight
        rows = DB.ExecuteDB(f"Select Action, BanDays, Message FROM Policies WHERE [From] <= {Weight} and [To] >= {Weight}")
        if len(rows) > 0:
            return {'Action':rows[0][0], 'BanDays': rows[0][1], 'Message':rows[0][2], 'Weight':Weight}
        Log(f"Couldn't find a Policy entry for Weight {Weight}", bcolors.WARNING, logging.ERROR)
    else:
        Log(f"Couldn't find a RedditUser entry for ActionId {ActionId}", bcolors.WARNING, logging.ERROR)
    return  {'Action':0, 'BanDays': '0', 'Message':'0', 'Weight':0}

def GetUserByID(ID):
    return DB.ExecuteDB(f"SELECT R.RedditName FROM Actions A join RedditUsers R on R.Id = A.RedditUserId where A.Id = {ID}")[0][0]
async def ResolveAction(sIn, ActionId, reddit, message):
    if not sIn.startswith('!'):
        return [Message(False,False,MessageType.Text,f"Selecciona un motivo !<Id>, <Descripcion (Opcional)> \n{GetActionTypes(GetUserByID(ActionId),sIn.strip(' '))}\nUndo - Deshacer warn.")]
    Input = SanatizeInput(sIn)
    Weight = ValidateActionType(DB, Input['Id'])
    if Weight > -1:
        ApplyingPol = GetApplyingPolicy(ActionId, Weight)
        if ApplyingPol['Action'] > 0:
            try:
                #Mark action as processing
                asyncio.Task(HandleMessage(int(os.getenv('DiscordMaxChars')),DB, message.channel ,Message(False,False,MessageType.Text,f"Procesando Warn ID {ActionId}...\nAplicando medida !{Input['Id']}")))
                DB.WriteDB(f"Update Actions set Processing = 1 where Id = {ActionId}")
                preparedAction = await ExecuteAction(reddit,Input['Id'],Input['Description'],ActionId,ApplyingPol['Message'])
                sRetu = await NotifyRedditUser(DB, reddit, preparedAction, ApplyingPol, ActionId,"Reddit")
                return [Message(False,False,MessageType.Text,sRetu)]
            except Exception as err:
                Log(f"An error occurred while trying to delete submission for action Id {ActionId}:\n{sys.exc_info()[1]}",bcolors.WARNING,logging.ERROR)
                #unmark processing
                DB.WriteDB(f"Update Actions set Processing = null where Id = {ActionId}")
                return [Message(False,False,MessageType.Text,f"Ocurrio un error al intentar borrar el post: {sys.exc_info()[1]}")]

        return [Message(False,False,MessageType.Text,"Error al buscar politica")]
    else:
        return [Message(False,False,MessageType.Text,"Formato incorrecto, por favor ingresa el motivo usando los IDs correspondientes")]

async def ExecuteAction(reddit, InputId, InputDesc, ActionId, Message):
    try:
        
        ActionDetailRow = GetCommonActionDetails(DB, "ActionId",ActionId)[0]
        LinkType = GetLinkType(f"https://{ActionDetailRow['Link']}")
        if LinkType == 1:
            submission = asyncpraw.models.Submission(reddit,url = f"https://{ActionDetailRow['Link']}")
        elif LinkType == 2:
            submission = asyncpraw.models.Comment(reddit,url = f"https://{ActionDetailRow['Link']}")
            asyncio.Task(SaveSnapshot(submission,ActionId))
        if LinkType != 0:
            asyncio.Task(RemoveSubAndChildren(submission))
        DB.WriteDB(f"UPDATE Actions SET Processing = null, ActionType = ?, Description = ? WHERE Id = ?;", (InputId,InputDesc,ActionId))
        ActionDetailRow = GetCommonActionDetails(DB, "ActionId",ActionId)[0]
        modmail = await CreateModMail(Message, ActionDetailRow['Link'],ActionDetailRow['TypeDesc'],ActionDetailRow['Details'],ActionDetailRow['User'],ActionDetailRow['RuleLink'], ActionDetailRow['Snapshot'], reddit, DB)
        return {'ActionDetailRow': ActionDetailRow, 'ModMail': modmail}
    except Exception as err:
        raise ExecuteActionException(f"Error while trying to execute Action {ActionId}:\r{err}")
async def SaveSnapshot(Comment, ActionId):
    await Comment.load()
    snapshot = ""
    while type(Comment) == asyncpraw.models.reddit.comment.Comment:
        snapshot = f"[{datetime.fromtimestamp(Comment.created_utc).strftime('%Y-%m-%d %H:%M:%S')}] {GetAuthorName(Comment)}:\r\n\t{Comment.body}\r\n{snapshot}"
        Comment = await Comment.parent()
        await Comment.load()
    DB.WriteDB( f"UPDATE Actions SET Snapshot = ? where Id =?",(snapshot,ActionId))
async def RemoveSubAndChildren(submission):
    await submission.load()
    if type(submission) == asyncpraw.models.reddit.comment.Comment:
        await submission.refresh()
        replies = submission.replies.list()
    else:
        await submission.comments.replace_more(0)
        replies = submission.comments.list()
    for sub in replies:
        if type(sub) == asyncpraw.models.reddit.comment.Comment and GetAuthorName(sub) == submission.author.name:
            await sub.mod.remove()
    await submission.mod.remove()
def GetAuthorName(submission):
    if submission is not None and submission.author is not None:
        return submission.author.name
    return "[Usuario Eliminado]"
async def GetModmailObj(Link):
    sSubs = DB.GetSetting("subreddit") #Checked
    for sSub in sSubs:
        oSub = await reddit.subreddit(sSub)
        modmail = await oSub.modmail(SanatizeRedditLink(Link).rsplit('/',1)[1])
        if modmail is not None:
            return modmail
    return None
async def InitAction(Link, reddit, SenderAction):
    try:
        linkType = GetLinkType(Link)
        if linkType > 0:
            if linkType == 3:  #Modmail
                modmail = await GetModmailObj(Link)
                if modmail is None:
                    return [Message(False,True,MessageType.Text,f"Modmail no encontrado.")]
                AuthorName = modmail.participant.name  # This returns a ``Redditor`` object.
                Link = f"reddit.com/message/messages/{modmail.legacy_first_message_id}"
            rows = GetCommonActionDetails(DB, "Link",SanatizeRedditLink(Link))
            if len(rows) > 0:
                if rows[0]['TypeDesc'] is None:
                    return [Message(False,True,MessageType.Text,f"Ese link esta a la espera de que el Moderador {rows[0]['DiscordId']} elija el motivo de la sancion.")]
                return [Message(False,False,MessageType.Text,f"Ese link ya fue sancionado por Mod: {rows[0]['ModName']}\nId: {rows[0]['Id']}\nFecha: {rows[0]['Date']} \nMotivo: {rows[0]['TypeDesc']}\nDetalles: {rows[0]['Details']}")]
            else:
                if linkType == 1:
                    submission = asyncpraw.models.Submission(reddit,url = Link)
                    await submission.load()
                    AuthorName = GetAuthorName(submission)
                elif linkType == 2:
                    comment = asyncpraw.models.Comment(reddit,url = Link)
                    await comment.load()
                    AuthorName = GetAuthorName(comment)  # This returns a ``Redditor`` object.
                if AuthorName == "[Usuario Eliminado]":
                    if submission == None:
                        comment.mod.remove()
                    else:
                        submission.mod.remove()
                    msgRetu = [Message(False,False,MessageType.Text,f"El usuario elimino su cuenta, no se sancionara al usuario pero el contenido sera eliminado")]
                else:
                    RUid = await GetRedditUID(AuthorName)
                    row = (SanatizeRedditLink(Link), SenderAction.Id,datetime.now(),RUid)
                    msgRetu = GetWarns(AuthorName, True)
                    DB.WriteDB("""INSERT INTO Actions (Link, Mod, Date, RedditUserId) VALUES (?,?,?,?);""", row)
                    msgRetu.append(Message(False,False,MessageType.Text,f"Selecciona un motivo !<Id>, <Descripcion (Opcional)> \n{GetActionTypes(AuthorName)}\nUndo - Deshacer warn."))
                return msgRetu
        return []
    except:
        return [Message(False,False,MessageType.Text,f"Error al intentar iniciar la accion: {sys.exc_info()[1]}")]
async def GetRedditUID(sName):
    UID = DB.GetDBValue(f"Select Id from RedditUsers where RedditName = '{sName}'")
    if UID is None:
        oUser = await reddit.redditor(sName)
        try:
            await oUser.load()
            mDeleted = False
            if hasattr(oUser, 'created_utc') and oUser.created_utc is not None:
                sTime = datetime.fromtimestamp(oUser.created_utc).strftime('%Y-%m-%d')
            else:
                sTime = None
            if hasattr(oUser, 'is_suspended') and oUser.is_suspended:
                mActive = 0
            else:
                mActive = sTime != None
            DB.WriteDB("Insert into RedditUsers (RedditName, CakeDay, Active) values(?,?,?)",(oUser.name, sTime, mActive))
        except:
            DB.WriteDB("Insert into RedditUsers (RedditName, CakeDay, Active) values(?,?,?)",(sName, None, 0))
            #deleted account
        return DB.GetDBValue(f"Select Id from RedditUsers where RedditName = '{sName}'")
    else:
        return UID
client.run(TOKEN)