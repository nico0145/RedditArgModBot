import os
import sqlite3 as sl
import discord
import asyncpraw
import sys
import asyncio
import threading
from prawcore.exceptions import OAuthException, ResponseException
from dotenv import load_dotenv
from Reddit import get_reddit_object
from datetime import datetime
from datetime import timedelta, date
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from dateutil.relativedelta import *
from DBHandle import *
from StaticHelpers import *
class Message:
    def __init__(self,Embed, NoDel, Type, Content):
        self.Embed = Embed
        self.NoDel = NoDel
        self.Type = Type
        self.Content = Content
class MessageType:
    Text = 1
    Image = 2
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
    while True:
        try:
            seconds = int(DB.GetSetting("RefreshModMail"))
            if seconds > 0:
                await asyncio.sleep(seconds)
            #get all new modmails
            #search for their IDs on DB where  db.modmailID = ID and db.LastUpdated < last_user_update
            #foreach
            #   send discord message @discordmod with the mod mail link and the reddit message/post link
            #   update db record LastUpdated =  last_user_update
            #unreadMail = await reddit.subreddit(DB.GetSetting("subreddit")).modmail.conversations(sort="unread")
            sQuery = ""
            #print(f"Unread Mail:\n")
            sub = await reddit.subreddit(DB.GetSetting("subreddit"))
            async for mail in sub.modmail.conversations(sort="unread"):
                #print(f"Mail Id: {mail.id}\tLast User Update: {mail.last_user_update}\n")
                if mail.last_user_update is not None and mail.last_mod_update is not None and mail.last_mod_update >= mail.last_user_update:
                    await mail.read()
                else:
                    sQuery += f" or (a.modmailID = '{mail.id}' and ifnull(a.LastModmailUpdated,'{mail.last_user_update}')  <= '{mail.last_user_update}')"
            sQuery = f"select a.User, '<@' ||  m.DiscordID ||  '>', 'https://mod.reddit.com/mail/inbox/'|| a.modmailID,'https://'|| a.Link, at.Description, a.Id, a.LastModmailUpdated from Actions a join Moderators m on m.Id = a.Mod join ActionType at on at.Id = a.ActionType where {sQuery[4:]}"
            rows = DB.ExecuteDB(sQuery)
            #print(f"Query: '{sQuery}'\nDB Matches: {len(rows)}\n")
            if len(rows) > 0:
                channel = client.get_channel(int(DB.GetSetting("GaryChannel")))
            for row in rows:
                #print(f"{row[1]}: {row[0]} Respondio al modmail generado por:\n{row[3]}\nSancion: {row[4]}\nClickea en el siguiente link para responder\n{row[2]}\nLastModmailUpdated: {row[6]}\nQuery criteria: [{sQuery}")
                embMsg = discord.Embed()
                embMsg.description = f"[u/{row[0]}](https://www.reddit.com/user/{row[0]}/) Respondio al modmail generado por:\n[{row[4]}]({row[3]})\nClickea [Aqui]({row[2]}) para responder"
                sentMsg = await channel.send(row[1], embed=embMsg)
                DB.WriteDB(f"Update Actions set LastModmailUpdated = '{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f+00:00')}' WHERE Id = {row[5]}")
        except:
            print(f"Ocurrio un error al intentar obtener modmails de la API de Reddit: {sys.exc_info()[1]}")
@client.event
async def on_ready():
    print(f'{client.user.name} has connected to Discord!')
    rres = await async_get_reddit_object()
    if rres['status'] == 'success':
        global reddit
        reddit = rres['data']
    else:
        print(rres['data'])
    await CheckModmail()
    loop = asyncio.get_event_loop()
    loop.run_forever()

@client.event
async def on_message(message):
    Response = None
    if message.author == client.user:
        return
    SenderAction = CheckSender(message.author)
    if SenderAction['modID'] != '0': 
        StandardMessage = message.content.lower()
        if StandardMessage.strip(' ')=="gary":
            Response = [Message(False,False,MessageType.Text,"gary - Muestra esta ayuda\nwarns <user> - Muestra los warns de un usuario\nunwarn <id> - Elimina un warn especifico\nunban <user> - desbannea a un usuario\napproveuser <user> - Agrega a un usuario a la lista de usuarios aprobados\nmods - funciones de moderador\nsettings - configura las preferencias\npolicies - configura las politicas de moderacion\nreasons - configura los motivos de sancion\nstats - Muestra estadisticas de moderacion\nschedposts - Muestra los posts programados\n<link> - inicia el proceso de warn")]
        elif StandardMessage.startswith('warns '):
            Response = GetWarns(message.content[6:].strip(' '))
        elif StandardMessage.startswith('unwarn '):
            Response = Unwarn(message.content[7:].strip(' '))
        elif StandardMessage.startswith('unban '):
            Response = await Unban(message.content[6:].strip(' '), reddit)
        elif StandardMessage.startswith('approveuser '):
            Response = await ApproveUser(message.content[11:].strip(' '), reddit)
        elif StandardMessage.startswith('mods'):
            #MassSanatizeLinks() this is here if we need to run a mass sanatization if reddit changes the URL formats or something
            Response = HandleMods(message.content[5:].strip(' '))
        elif StandardMessage.startswith('settings'):
            Response = HandleSettings(message.content[9:].strip(' '))
        elif StandardMessage.startswith('policies'):
            Response = HandlePolicies(message.content[9:].strip(' '))
        elif StandardMessage.startswith('reasons'):
            Response = HandleReasons(message.content[8:].strip(' '))
        elif StandardMessage.startswith('stats'):
            Response = await HandleStats(message.content[6:].strip(' '), SenderAction['modID'], reddit)
        elif StandardMessage.startswith('schedposts'):
            Response = await HandleSchedposts(message.content[10:].strip(' '), reddit)
        elif StandardMessage.strip(' ')=="undo":
            if SenderAction['status'] > 0:
                DeletePending(SenderAction['status'])
                Response = [Message(False,False,MessageType.Text,f"WarnID {SenderAction['status']} pendiente eliminado.")]
            else:
                Response = [Message(False,False,MessageType.Text,"No hay warnings pendientes.")]
        else:
            if SenderAction['status'] == 0:
                Response = await InitAction(message.content, reddit, SenderAction)
            else:
                linkType = GetLinkType(message.content)
                if linkType != 0:
                    DeletePending(SenderAction['status']) #el mod mando otro link en vez de responder, borrar lo pendiente y hacer uno nuevo
                    Response = await InitAction(message.content, reddit, SenderAction)
                else:
                    Response = await ResolveAction(message.content, SenderAction['status'], reddit)
        for IndResponse in Response:
            asyncio.Task(HandleMessage(message,IndResponse))
            await asyncio.sleep(1)


    if message.content == 'raise-exception':
        raise discord.DiscordException
    #def GetModLog(reddit, user):
    #    target_author
    #    mod
    #    action
    #    target_permalink
    #    created_utc
async def HandleMessage(message, Response):
    Msgs = []
    bEmbed = False
    if Response.Type == MessageType.Text:
        for indRes in Sectionize(Response.Content, "--------------------", True):
            if Response.Embed:
                embMsg = discord.Embed()
                embMsg.description = indRes
                sentMsg = await message.channel.send(embed=embMsg)
            else:
                sentMsg = await message.channel.send(indRes)
            Msgs.append(sentMsg)
    elif Response.Type == MessageType.Image:
        sentMsg = await message.channel.send(file=discord.File(Response.Content))
        Msgs.append(sentMsg)
    seconds = int(DB.GetSetting("DelMsgAfterSeconds"))
    if seconds > 0 and not Response.NoDel:
        await asyncio.sleep(seconds)
        for Msg in Msgs:
            await Msg.delete()

def Sectionize(sIn, sSplit, UseNewLinesForChunks):
    Max = int(os.getenv('DiscordMaxChars'))
    sIn = sIn.strip("\n")
    chunks = sIn.split(sSplit)
    retChunks = []
    sRet = ""
    for chunk in chunks:
        chunk = chunk.strip("\n")
        if len(chunk) > 0:
            if(UseNewLinesForChunks):
                sSeparator = f"\n{sSplit}\n"
            else:
                sSeparator = sSplit
            if len(sRet + chunk + sSeparator) > Max:
                if len(sRet) == 0: #this chunk is larger than the limit by itself, cut it in pieces 
                    if UseNewLinesForChunks:
                        spaceChunks = Sectionize(chunk,"\n",False)
                        for spaceChunk in spaceChunks:
                            if len(spaceChunk) > Max:
                                CutStringInPieces(spaceChunk, Max, retChunks)
                            elif len(spaceChunk) > 0:
                                retChunks.append(spaceChunk)
                    else:
                        CutStringInPieces(chunk, Max, retChunks)
                else: #The concat of chunks went over the limit on this set, don't use this last chunk for now, add it to the next set
                    retChunks.append(sRet)
                    sRet = chunk + sSeparator
            else:
                sRet = sRet + chunk + sSeparator
    if len(sRet) > 0:
        retChunks.append(sRet.rstrip(sSeparator))
    if UseNewLinesForChunks: #Esta funcion esta bien pero hasta ahi nomas, si tenes un cacho de exacto 2000 caracteres y tenes que agregarle las comillas discord te va a romper la pija,
                             #lo ideal seria verificar esto mientras estas armando los cachos mas arriba pero toda la paja
        iAux = 0
        TabSymb = '```'
        OpenTable = False
        while iAux < len(retChunks):
            if OpenTable:
                retChunks[iAux] = TabSymb + retChunks[iAux]
                OpenTable = False
            if retChunks[iAux].count(TabSymb) % 2 != 0: # Si esto es verdadero tenes que cerrar la tabla en este cacho y abrirla en el siguiente
                retChunks[iAux] +=TabSymb
                OpenTable = True
            iAux +=1

    return retChunks
def MassSanatizeLinks():
    rows = DB.ExecuteDB(f"SELECT Id, Link FROM Actions")
    sSub = DB.GetSetting("subreddit").lower()
    for row in rows:
        DB.WriteDB(f"Update Actions set [Link] = '{SanatizeRedditLinkSub(row[1], sSub)}' WHERE Id = {row[0]}")
def CutStringInPieces(chunk, Max, retChunks):
    while len(chunk) > Max:
        retChunks.append(chunk[:Max])
        chunk = chunk[Max:]
    retChunks.append(chunk)
def SanatizeRedditLinkSub(sIn,subReddit):
    sIn = sIn.lstrip('http')
    sIn = sIn.lstrip('s')
    sIn = sIn.lstrip('://')
    sIn = sIn.lstrip('www.')
    sIn = sIn.lstrip('old.') 
    if (sIn.startswith('reddit.com') and (subReddit in sIn.lower() or 'message' in sIn.lower())) or sIn.startswith('mod.reddit.com/mail'):
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

def SanatizeRedditLink(sIn):
    return SanatizeRedditLinkSub(sIn, DB.GetSetting("subreddit").lower())   
def HandleReasons(sCommand):
    if sCommand.lower().startswith('list'):
        return GetReasons()
    if sCommand.lower().startswith('edit '):
        return EditReason(sCommand[4:].strip(' '))
    if sCommand.lower().startswith('remove '):
        return RemoveReason(sCommand[6:].strip(' '))
    if sCommand.lower().startswith('setdefaultmessage '):
        return DefaultMessageReason(sCommand[17:].strip(' '))
    else:
        return [Message(False,False,MessageType.Text,"reasons list - Muestra un listado de los motivos\nreasons remove <id> - Elimina un motivo\nreasons edit <id (entero, si esta vacio es un nuevo registro)>,<Descripcion(texto)>,<Peso(entero)> - Agrega o edita un motivo\nreasons setdefaultmessage <id (entero)>,<Descripcion(texto)> - Agrega (o quita si esta vacio) un mensaje por defecto a los motivos")]
def DefaultMessageReason(sCommand):
    sCommand = sCommand.replace("\,","[Coma]")
    sParams = sCommand.split(',')
    if len(sParams) == 2 and check_int(sParams[0].strip(' ')):
        sId = sParams[0].strip(' ')
        sDescription = sParams[1].replace("[Coma]",",").strip(' ')
        DB.WriteDB(f"Update ActionType set [DefaultMessage] = '{sDescription}' where Id = {sId}",row)
        return [Message(False,False,MessageType.Text,"Motivo agregado")]
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
                    return [Message(False,False,MessageType.Text,f"Motivo #{sId} actualizado.")]
                return [Message(False,False,MessageType.Text,f"Motivo #{sId} no encontrado.")]
    return [Message(False,False,MessageType.Text,f"Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\n<id(entero, si esta vacio es un nuevo registro)>,<Descripcion(texto)>,<Peso(entero)>\nPara insertar comas [,] en los campos de texto usar el caracter de escape \\\,")]
def RemoveReason(sId):
    if not check_int(sId):
        return [Message(False,False,MessageType.Text,"Id Incorrecto")]
    iId = int(sId)
    rows = DB.ExecuteDB(f"SELECT * FROM ActionType where Id = {iId}")
    if len(rows) > 0:
        DB.WriteDB(f"Update ActionType set Active = 0 WHERE Id = {iId}")
        return [Message(False,False,MessageType.Text,f"Motivo #{iId} eliminado.")]
    return [Message(False,False,MessageType.Text,f"Motivo #{iId} no encontrado.")]
def GetReasons():
    rows = DB.ExecuteDB(f"SELECT * FROM ActionType where Active = 1")
    sRetu = ""
    for row in rows:
        sRetu = sRetu + f"Id: {row[0]}\nDescription: {row[1]}\nPeso: {row[2]}\n--------------------\n"
    return [Message(False,False,MessageType.Text,sRetu)]

async def HandleSchedposts(sCommand, reddit):
    if sCommand.lower().startswith('list'):
        return await GetSchedPostList(reddit)
    if sCommand.lower().startswith('details'):
        return await GetSchedPostDetails(reddit, sCommand[8:].strip(' '))
    if sCommand.lower().startswith('post'):
        return await MnuPostSchedPost(reddit, sCommand[5:].strip(' '))
    if sCommand.lower().startswith('edit'):
        return [Message(True,False,MessageType.Text,"Para editar los posts recursivos hace click [Aqui](https://www.reddit.com/r/argentina/about/wiki/scheduledposts)")]
    else:
        return [Message(False,False,MessageType.Text,"schedposts list - Muestra la lista de posts programados\nschedposts details <ID(entero)> - Muestra los detalles del post programado\nschedposts post <ID(entero)> - Postea un post programado\nschedposts edit - Muestra el link a la wiki en donde configurar los posts programados")]
async def GetSchedPostList(reddit):
    schedPosts = await GetSchedPosts(reddit)
    sRetu = ""
    for schedpost in schedPosts.SchedPosts:
        sRetu = f"{sRetu}#{schedpost.Id} - {schedpost.Title}\r\n"
    return [Message(False,False,MessageType.Text,sRetu)]
async def GetSchedPosts(reddit):
    subreddit = await reddit.subreddit(DB.GetSetting("subreddit"))
    wiki = await subreddit.wiki.get_page("scheduledposts")
    return GetSchedPostsFromWiki(wiki)
async def MnuPostSchedPost(reddit, sCommand):
    if not sCommand.isnumeric():
        return [Message(False,False,MessageType.Text,"Id Incorrecto")]
    iId = int(sCommand)
    schedPosts = await GetSchedPosts(reddit)
    subreddit = await reddit.subreddit(DB.GetSetting("subreddit"))
    Filtered = filter(lambda x: x.Id == iId, schedPosts.SchedPosts)
    Posted = False
    sRet = ""
    for Post in Filtered:
        Post.nextTime = "N/A"
        if await PostSchedPost(DB, reddit, subreddit, Post):
            RedditPostId = DB.GetDBValue(f"select PostID from ScheduledPosts where RedditID = {Post.Id} order by PostedDate desc limit 1")
            sRet = f"{sRet}Post [{Post.Title}](https://www.reddit.com/r/argentina/comments/{RedditPostId}/_/) Creado correctamente\n"
    if len(sRet) > 0:
        return [Message(True,True,MessageType.Text,sRet)]
    else:
        return [Message(False,False,MessageType.Text,"Hubo un error al crear el post, consulta los logs")]
async def GetSchedPostDetails(reddit, sCommand):
    if not sCommand.isnumeric():
        return [Message(False,False,MessageType.Text,"Id Incorrecto")]
    iId = int(sCommand)
    schedPosts = await GetSchedPosts(reddit)
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
        msgRetu.append(Message(False,False,MessageType.Text,f"**Estadisticas del mod {sCommand}**\n" + DB.GetTable(f"Select at.Description as Motivo, count(1) as Cantidad from Actions A join Moderators M on M.Id = A.Mod join ActionType AT on A.ActionType = AT.Id Where lower(M.Name) = '{sCommand}' group by at.Description order by Cantidad desc")))
        plot = GetModYearLog(sCommand,'plot.png')
        if len(plot) > 0:
            msgRetu.append(Message(False,False,MessageType.Image,plot))
        plot = GetModMonthLog(sCommand,'plotm.png')
        if len(plot) > 0:
            msgRetu.append(Message(False,False,MessageType.Image,plot))
        plot = GetModHourLog(sCommand,'ploth.png', ModID)
        if len(plot) > 0:
            msgRetu.append(Message(False,False,MessageType.Image,plot))
    else:
        msgRetu.append(Message(False,False,MessageType.Text,"**Estadisticas de Moderadores**\n" + DB.GetTable("select t1.Moderador, t1.Cantidad, t2.Puntos, printf(\"%.2f\", t2.Puntos*1.0 / t1.Cantidad*1.0) as PuntosPorAccion from  (select m.Name as Moderador, count(1) as Cantidad from Actions A join Moderators M on M.Id = A.Mod group by m.Name) t1 join (select m.Name as Moderador, sum(AT.Weight) as Puntos from Actions A join ActionType AT on A.ActionType = AT.Id join Moderators M on M.Id = A.Mod group by m.Name) t2 on t2.Moderador =t1.Moderador order by PuntosPorAccion desc") + "\n\n"))
    return msgRetu
def GetModYearLog(sCommand, pltName, lineLabel = '', new = True):
    sQuery =    "select sum(cnt) as cnt, mes From(" \
                "select count(1) as 'cnt', strftime(\"%m-%Y\", a.Date) as 'mes' "\
                "from Actions A "\
                "join Moderators M on M.Id = A.Mod "\
                f"where lower(M.name) = '{sCommand.lower()}' "\
                "and a.Date > DATE(Date(),'-1 years') "\
                "group by mes "\
                "union "\
                "select count(1) as 'cnt', strftime(\"%m-%Y\", ML.Date) as 'mes' "\
                "from ModLog ML "\
                "join Moderators M on lower(M.redditname) = lower(ML.ModName) "\
                f"where lower(M.Name) = '{sCommand.lower()}' and ML.Date > DATE(Date(),'-1 years') "\
                "and (ML.Action like 'approve%' or ML.Action like 'remove%') "\
                "group by mes)H group by mes"
    if new == False:
        return CreateLinePlot(sQuery,pltName, 'Mes', 'Cantidad de Acciones', 'Acciones por Mes', new, lineLabel)
    CreateLinePlot(sQuery,pltName, 'Mes', 'Cantidad de Acciones', 'Acciones por Mes', new,lineLabel = "Aprobados",fill = True)
    sQuery =    "select sum(cnt) as cnt, mes From(" \
                "select count(1) as 'cnt', strftime(\"%m-%Y\", a.Date) as 'mes' "\
                "from Actions A "\
                "join Moderators M on M.Id = A.Mod "\
                f"where lower(M.name) = '{sCommand.lower()}' "\
                "and a.Date > DATE(Date(),'-1 years') "\
                "group by mes "\
                "union "\
                "select count(1) as 'cnt', strftime(\"%m-%Y\", ML.Date) as 'mes' "\
                "from ModLog ML "\
                "join Moderators M on lower(M.redditname) = lower(ML.ModName) "\
                f"where lower(M.Name) = '{sCommand.lower()}' and ML.Date > DATE(Date(),'-1 years') "\
                "and (ML.Action like 'remove%') "\
                "group by mes)H group by mes"
    return CreateLinePlot(sQuery,pltName, 'Mes', 'Cantidad de Acciones', 'Acciones por Mes', False, lineLabel = "Removidos",fill = True)
def GetModMonthLog(sCommand, pltName, lineLabel = '', new = True):
    fig, ax = plt.subplots()
    fmt_day = mdates.DayLocator(interval = 5)
    ax.xaxis.set_major_locator(fmt_day)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
    sQuery =    "select sum(cnt) as cnt, dia From(" \
                "select count(1) as 'cnt', strftime(\"%Y-%m-%d\", a.Date) as 'dia' "\
                "from Actions A "\
                "join Moderators M on M.Id = A.Mod "\
                f"where lower(M.name) = '{sCommand.lower()}' "\
                "and a.Date > DATE(Date(),'-1 months') "\
                "group by dia "\
                "union "\
                "select count(1) as 'cnt', strftime(\"%Y-%m-%d\", ML.Date) as 'dia' "\
                "from ModLog ML "\
                "join Moderators M on lower(M.redditname) = lower(ML.ModName) "\
                f"where lower(M.Name) = '{sCommand.lower()}' and ML.Date > DATE(Date(),'-1 months') "\
                "and (ML.Action like 'approve%' or ML.Action like 'remove%') "\
                "group by dia)H group by dia order by dia"
    if new == False:
        return CreateLinePlot(sQuery,pltName, 'Dia', 'Cantidad de Acciones', 'Acciones por Dia', new, lineLabel,isXDateFormat="%Y-%m-%d")
    CreateLinePlot(sQuery,pltName, 'Dia', 'Cantidad de Acciones', 'Acciones por Dia', new,lineLabel = "Aprobados",fill = True,isXDateFormat="%Y-%m-%d")
    sQuery =    "select sum(cnt) as cnt, dia From(" \
                "select count(1) as 'cnt', strftime(\"%Y-%m-%d\", a.Date) as 'dia' "\
                "from Actions A "\
                "join Moderators M on M.Id = A.Mod "\
                f"where lower(M.name) = '{sCommand.lower()}' "\
                "and a.Date > DATE(Date(),'-1 months') "\
                "group by dia "\
                "union "\
                "select count(1) as 'cnt', strftime(\"%Y-%m-%d\", ML.Date) as 'dia' "\
                "from ModLog ML "\
                "join Moderators M on lower(M.redditname) = lower(ML.ModName) "\
                f"where lower(M.Name) = '{sCommand.lower()}' and ML.Date > DATE(Date(),'-1 months') "\
                "and (ML.Action like 'remove%') "\
                "group by dia)H group by dia order by dia"
    sRet = CreateLinePlot(sQuery,pltName, 'Dia', 'Cantidad de Acciones', 'Acciones por Dia', False, lineLabel = "Removidos",fill = True,isXDateFormat="%Y-%m-%d")
    ax.format_xdata = mdates.DateFormatter('%d/%m')
    fig.autofmt_xdate()
    plt.savefig(pltName)
    return sRet
def GetModHourLog(sCommand, pltName, ModId, lineLabel = '', new = True):
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
            f"	select count(1) as Cantidad,cast(strftime(\"%H\", DATETIME(DATETIME(a.Date,'-'||(select Value from Settings where [Key]= 'HusoHorarioDB')||' hours' ), (select TimeZone from Moderators where Id = {ModId})|| ' hours')) as INTEGER) as Hora  "\
            "	from Actions A  "\
            "	join Moderators M on M.Id = A.Mod  "\
            f"	where lower(M.name) = '{sCommand.lower()}' and a.Date > DATE(Date(),'-1 years')  "\
            "	group by Hora "\
            "	union  "\
            "	select count(1) as Cantidad,  "\
            "	cast(strftime(\"%H\", DATETIME(ML.Date, (select TimeZone from Moderators where Id = 1)|| ' hours')) as INTEGER) as Hora  "\
            "	from ModLog ML "\
            "   join Moderators M on lower(M.redditname) = lower(ML.ModName) "\
            f"	where lower(M.Name) = '{sCommand.lower()}' and ML.Date > DATE(Date(),'-1 years')  "\
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
    sRetu = [Message(False,False,MessageType.Text,f"**Top {str(Limite)} usuarios con mas acciones**\n" + DB.GetTable(f"select User, count(1) as Cantidad from Actions group by User order by Cantidad desc LIMIT {Limite}"))]
    sRetu.append(Message(False,False,MessageType.Text, f"**Cantidad de usuarios por cantidad de acciones**\n" + DB.GetTable(f"Select Cantidad as CantidadDeFaltas, count(User) as Usuarios from (select A.User, count(1) as cantidad from Actions A join ActionType AT on AT.Id = A.ActionType where AT.Weight > 0 group by A.User) as Users group by Cantidad")))
    return sRetu
async def HandleIndUserStats(reddit, sCommand):
    oUser = await reddit.redditor(sCommand)
    sSubreddit = DB.GetSetting("subreddit").lower()
    await oUser.load()
    submissions = []
    async for comment in oUser.comments.new(limit=None):
        if comment.subreddit_name_prefixed == "r/" + sSubreddit:
            submissions.append(UserSubmission("comment",comment.created_utc, comment.score, comment.removed))
    async for post in oUser.submissions.new(limit=None):
        if post.subreddit_name_prefixed == "r/" + sSubreddit:
            submissions.append(UserSubmission("post",post.created_utc, post.score, post.removed))
    if len(submissions) == 0:
        return [Message(False,False,MessageType.Text,f"El usuario {sCommand} no participa del subrredit r/{sSubreddit}")]
    MsgsRetu = GetWarns(sCommand, True)
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
    MsgsRetu.append(Message(True,False,MessageType.Text,\
        f"**Cuenta Creada:** {AccountCreated.strftime('%Y-%m-%d')}\n**Participa en el sub desde:** {FirstDateOfParticipation.strftime('%Y-%m-%d')}\n"\
        f"**Comentarios**\n---**Cantidad:** {CommentCount}\n---**Karma: **{CommentKarma}\n---**Porcentaje de removidos:** {'{0:.3g}'.format(CommentPercRemoved)}%\n"\
        f"**Posts**\n---**Cantidad:** {PostCount}\n---**Karma: **{PostKarma}\n---**Porcentaje de removidos:** {'{0:.3g}'.format(PostPercRemoved)}%\n"\
        f"**Submissiones promedio por dia:** {'{0:.3g}'.format(subsPerDay)}"))    
    return MsgsRetu
def HandleSubStats(sCommand, ModId):
    sRetu = [Message(False,False,MessageType.Text,f"**Modmail**\n" + DB.GetTable(f"select a1.Enviados, a2.Respondidos, printf(\"%.2f\",(100.00*a2.Respondidos)/a1.Enviados) as PorcentajeRespondidos from (select count(1) as Enviados,'a' as a from actions where Modmailid is not null) a1 join (select count(1) as Respondidos ,'a' as a from actions where lastmodmailupdated  is not null) a2 on a1.a = a2.a"))]
    sRetu.append(Message(False,False,MessageType.Text, f"**Cantidad de Acciones tomadas**\n" + DB.GetTable(f"select AT.Description as Descripcion, count(1) as Cantidad from Actions A join ActionType AT on AT.Id = A.ActionType group by AT.Description order by Cantidad desc")))
    #sRetu.append(Message(False,False,MessageType.Text, f"**Acciones por dia de la semana**\n" + DB.GetTable("select case DDW when '0' then 'Domingo' when '1' then 'Lunes' when '2' then 'Martes' when '3' then 'Miercoles' when '4' then 'Jueves' when '5' then 'Viernes' when '6' then 'Sabado' end as DiaDeLaSemana, Cantidad from (SELECT strftime('%w',Date) DDW, count(1) as Cantidad from actions group by DDW)") + "\n"))
    
    
    plot = CreateLinePlot(f"select count(1) as 'cnt', strftime(\"%m-%Y\", a.Date) as 'mes' from Actions A where a.Date > DATE(Date(),'-1 years') group by strftime(\"%m-%Y\", a.Date)",'plot.png', 'Mes', 'Cantidad de Medidas', 'Medidas por Mes')
    if len(plot) > 0:
        sRetu.append(Message(False,False,MessageType.Image,plot))

    plot = CreateLinePlot(f"select count(1) as 'cnt', strftime(\"%m-%Y\", a.Date) as 'mes' from Actions A join ActionType AT on AT.Id = A.ActionType where AT.Weight > 0 and a.Date > DATE(Date(),'-1 years') group by strftime(\"%m-%Y\", a.Date)",'plotp.png', 'Mes', 'Cantidad de Medidas', 'Medidas punitivas por Mes')
    if len(plot) > 0:
        sRetu.append(Message(False,False,MessageType.Image,plot))

    rows = DB.ExecuteDB("SELECT Name FROM Moderators")
    plt.clf()
    for row in rows:
        plot = GetModYearLog(row[0],'ploty.png',row[0], False)
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
            f"		cast(strftime(\"%H\", DATETIME(DATETIME(a.Date,'-'||(select Value from Settings where [Key]= 'HusoHorarioDB')||' hours' ), (select TimeZone from Moderators where Id = {ModId})|| ' hours')) as INTEGER) as Hora  "\
            "		from Actions  "\
            "		A Join Moderators M on M.Id = A.Mod  "\
            "		where M.Active = 1 group by Hora "\
            "		union  "\
            "		select count(1) as Cantidad,  "\
            f"		cast(strftime(\"%H\", DATETIME(DATETIME(ML.Date,'-'||(select Value from Settings where [Key]= 'HusoHorarioDB')||' hours' ), (select TimeZone from Moderators where Id = {ModId})|| ' hours')) as INTEGER) as Hora  "\
            "		from ModLog ML "\
            "		Where ML.Date > DATE(Date(),'-1 years')  "\
            "		and (ML.Action like 'approve%' or ML.Action like 'remove%') "\
            "		group by Hora "\
            "		)group by Hora) counts on counts.Hora = cnt.x"
    plot = CreateLinePlot(sQuery,'ploth.png', 'Mes', 'Cantidad de Acciones', 'Acciones por Hora')
    if len(plot) > 0:
        sRetu.append(Message(False,False,MessageType.Image,plot))
    
    plt.clf()
    rows = DB.ExecuteDB("SELECT Name FROM Moderators where Active = 1")
    for row in rows:
        plot = GetModHourLog(row[0],'plotm.png', ModId,row[0], False)
    if len(plot) > 0:
        sRetu.append(Message(False,False,MessageType.Image,plot))
    
    return sRetu
def HandlePolicies(sCommand):
    if sCommand.lower().startswith('list'):
        return GetPolicies()
    if sCommand.lower().startswith('edit '):
        return EditPol(sCommand[4:].strip(' '))
    if sCommand.lower().startswith('remove '):
        return RemovePol(sCommand[7:].strip(' '))
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
    sub = await reddit.subreddit(DB.GetSetting("subreddit"))
    await sub.banned.remove(sUser)
    return [Message(False,False,MessageType.Text,f"Usuario {sUser} ha sido desbanneado.")]
async def ApproveUser(sUser, reddit):
    sub = await reddit.subreddit(DB.GetSetting("subreddit"))
    await sub.contributor.add(sUser)
    return [Message(False,False,MessageType.Text,f"Usuario {sUser} ha sido agregado a users aprobados.")]
def HandleMods(sCommand):
    if sCommand.lower().startswith('list'):
        return GetMods()
    if sCommand.lower().startswith('add '):
        return AddMod(sCommand[4:].strip(' '))
    if sCommand.lower().startswith('remove '):
        return RemoveMod(sCommand[7:].strip(' '))
    else:
        return [Message(False,False,MessageType.Text,"mods list - Muestra un listado de los moderadores\nmods add <nombre>,<nombre en reddit>,<ID de discord (numerico)> <Huso horario (numerico)> - Agrega un moderador\nmods remove <id> - Elimina un moderador por ID")]
def HandleSettings(sCommand):
    if sCommand.lower().startswith('list'):
        return GetSettings()
    if sCommand.lower().startswith('edit '):
        return EditSetting(sCommand[5:].strip(' '))
    else:
        return [Message(False,False,MessageType.Text,"settings list - Muestra un listado de preferencias\nsettings edit <setting> <value> - Edita una preferencia")]
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

def check_int(s):
    if s is not None and len(str(s)) > 0:
        if str(s)[0] in ('-', '+'):
            return str(s)[1:].isdigit()
        return str(s).isdigit()
    return 0

def AddMod(sCommand):
    sParams = sCommand.split(',')
    if len(sParams) == 4:
        if sParams[2].strip(' ').isnumeric() and sParams[3].strip(' ').isnumeric() and len(sParams[0].strip(' ')) > 0 and len(sParams[1].strip(' ')) > 0:
            row = (sParams[0].strip(' '),sParams[1].strip(' '),sParams[2].strip(' '), sParams[3].strip(' '))
            DB.WriteDB(f"""INSERT INTO Moderators (Name, RedditName, DiscordID, TimeZone, Active) VALUES (?,?,?,?,1);""",row)
            return [Message(False,False,MessageType.Text,f"{sParams[0]} fue agregado a la lista de moderadores")]
    return [Message(False,False,MessageType.Text,"Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\n<nombre>,<nombre en reddit>,<ID de discord (numerico)>, <Huso Horario (numerico)>")]

def RemoveMod(sId):
    if not check_int(sId):
        return [Message(False,False,MessageType.Text,"Id Incorrecto")]
    iId = int(sId)
    rows = DB.ExecuteDB(f"SELECT IsAdmin FROM Moderators where Id = {iId}")
    if len(rows) > 0:
        if(rows[0][0] == 1):
            return [Message(False,False,MessageType.Text,"No podes remover a un administrador")]
        DB.WriteDB(f"Update Moderators set Active = false WHERE Id = {iId}")
        return [Message(False,False,MessageType.Text,f"Moderador #{iId} eliminado.")]
    return [Message(False,False,MessageType.Text,f"Moderador #{iId} no encontrado.")]

def GetMods():
    return [Message(False,False,MessageType.Text,DB.GetTable("SELECT Id, Name, RedditName, DiscordID, Active FROM Moderators"))]

def GetSettings():
    rows = DB.ExecuteDB(f"SELECT * FROM Settings")
    sRetu = ""
    for row in rows:
        sRetu = sRetu + f"Setting: {row[1]}\nValue: {row[2]}\n--------------------\n"
    return [Message(False,False,MessageType.Text,sRetu)]

def Unwarn(sId):
    if not sId.isnumeric():
        return [Message(False,False,MessageType.Text,"Id Incorrecto")]
    iId = int(sId)
    rows = GetActionDetail('', iId,'')
    if len(rows) > 0:
        DB.WriteDB(f"DELETE FROM Actions WHERE Id = {iId}")
        return [Message(False,False,MessageType.Text,f"Warn #{iId} eliminado.")]
    return [Message(False,False,MessageType.Text,f"Warn #{iId} no encontrado.")]

def GetWarns(sUser, summary = False):
    rows = GetActionDetail('', 0,sUser)
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
def GetWarnsUserReport(sUser, msgLen):
    rows = GetActionDetail('', 0,sUser)
    sRetu = ""
    dateFrom = datetime.now() - timedelta(days=int(DB.GetSetting("warnexpires")))
    iWeight = 0
    for row in rows:
        if datetime.strptime(row['Date'], '%Y-%m-%d %H:%M:%S.%f') >= dateFrom and row['Weight'] > 0:
            sRetu = sRetu + f"{row['Date'].split(' ')[0]}\t[{row['TypeDesc']}](https://{row['Link']})\tPuntos: {row['Weight']}\n\n"
            iWeight += row['Weight']
    sRetu = sRetu.rstrip("\n") + f" **<-- Nueva Falta**\n\n**Total**: {iWeight}"
    while len(sRetu) > msgLen:
        sRetu = sRetu[sRetu.find("\n") + 2:]
    return sRetu
def CheckSender(author):
    rows = DB.ExecuteDB(f"SELECT Id FROM Moderators WHERE DiscordID = {author.id} and Active = true")
    if len(rows) <= 0:
        return {'modID': '0', 'status': '0'} #not valid 
    modId = rows[0][0]
    rows = DB.ExecuteDB(f"SELECT Id FROM Actions WHERE Mod = {modId} and ActionType is null")
    if len(rows) <= 0:
        return {'modID': modId, 'status': 0} #nothing pending
    else:
        return {'modID': modId, 'status': rows[0][0]} # Pending resolution

def GetActionTypes(UserName, filter = "", FormatTable = False):
    sRetu = ""
    Weight = GetUsersCurrentWeight(UserName)
    sQuery = f"SELECT '#' || t.Id as Id, t.Description as Descripcion, case t.Weight when 0 then 'Advertencia' else case p.Action when 1 then 'Advertencia' when 2 then case p.BanDays when -1 then 'Ban Permanente' else 'Ban ' || p.BanDays || ' Dias' End End End as Accion, t.Weight as Puntos FROM ActionType t join Policies p on p.[From] <= t.Weight + {Weight} and p.[To] >= t.Weight + {Weight} Where t.Active = 1 and t.Description like '%{filter}%' order by trim(t.Description), t.Weight desc"
    if FormatTable:
        return DB.GetTable(sQuery)
    rows = DB.ExecuteDB(sQuery)
    for row in rows:
        sRetu = f"{sRetu}{row[0]} - {row[1]} - **Puntos:** {row[3]} - **Accion: {row[2]} **\n"
    return sRetu

def DeletePending(Id):
    DB.WriteDB(f"DELETE FROM Actions WHERE Id = {Id}")

def ValidateActionType(Id):
    rows = DB.ExecuteDB(f"SELECT Weight FROM ActionType WHERE Id = {Id} and Active = 1")
    if len(rows) > 0:
        return int(rows[0][0])
    return -1
def SanatizeInput(sIn):
    sOut = sIn.split(',')
    sDesc = ''
    if len(sOut) > 1:
        sDesc = sIn[len(sOut[0]):].strip(',').strip(' ')
    sId = sOut[0].strip(',').strip(' ')
    if sId.startswith('#'):
        sId = sId[1:]
        if(sId.isnumeric()):
            return {'Id': sId,'Description' : sDesc}
    return {'Id': '0','Description' : sDesc}
def GetUsersCurrentWeight(sUser):
    dateFrom = datetime.now() - timedelta(days=int(DB.GetSetting("warnexpires")))
    rows = DB.ExecuteDB(f"Select Sum(t.Weight) FROM Actions a Join ActionType t on t.Id = a.ActionType WHERE a.User = '{sUser}' and a.Date >= '{dateFrom}'")
    if(len(rows)) > 0 and check_int(rows[0][0]):
        return int(rows[0][0])
    return 0
def GetApplyingPolicy(ActionId, AddedWeight):
    rows = DB.ExecuteDB(f"Select User FROM Actions WHERE Id = {ActionId}")
    if len(rows) > 0:
        if AddedWeight > 0:
            Weight = GetUsersCurrentWeight(rows[0][0]) + AddedWeight
        else:
            Weight = AddedWeight
        rows = DB.ExecuteDB(f"Select Action, BanDays, Message FROM Policies WHERE [From] <= {Weight} and [To] >= {Weight}")
        if len(rows) > 0:
            return {'Action':rows[0][0], 'BanDays': rows[0][1], 'Message':rows[0][2]}
    return  {'Action':0, 'BanDays': '0', 'Message':'0'}

async def CreateModMail(sMessage, Link, ActionDesc, Details, sUser, reddit):
    sMessage = sMessage.replace("[Sub]", DB.GetSetting("subreddit"))
    sMessage = sMessage.replace("[Link]", f"https://{Link}")
    sMessage = sMessage.replace("[ActionTypeDesc]", ActionDesc)
    sMessage = sMessage.replace("[Details]", Details.replace("\n",">\n"))
    if "[Consultas]" in sMessage:
        sConsultas = await GetLastConsultasThread(reddit)
        sMessage = sMessage.replace("[Consultas]", sConsultas)
    if "[Summary]" in sMessage:
        sMessage = sMessage.replace("[Summary]", GetWarnsUserReport(sUser,1000- (len(sMessage) - len("[Summary]"))))
    sMessage = sMessage.replace("\\n", "\n")
    return sMessage[:1000]
async def GetLastConsultasThread(reddit):
    List = ""
    sub = await reddit.subreddit(DB.GetSetting("subreddit"))
    #Submissions = await reddit.subreddit(DB.GetSetting("subreddit")).search(query='author:Robo-TINA AND (title:Consultas OR title:Preguntas)',sort='new',limit=1)
    async for Submission in sub.search(query='author:Robo-TINA AND (title:Consultas OR title:Preguntas)',sort='new',limit=1):
        List += Submission.shortlink
    return List
def GetUserByID(ID):
    return DB.ExecuteDB(f"SELECT [User] FROM Actions where [Id] = {ID}")[0][0]
async def ResolveAction(sIn, ActionId, reddit):
    if not sIn.startswith('#'):
        return [Message(False,False,MessageType.Text,f"Selecciona un motivo #<Id>, <Descripcion (Opcional)> \n{GetActionTypes(GetUserByID(ActionId),sIn.strip(' '))}\nUndo - Deshacer warn.")]
    Input = SanatizeInput(sIn)
    Weight = ValidateActionType(Input['Id'])
    if Weight > -1:
        ApplyingPol = GetApplyingPolicy(ActionId, Weight)
        if ApplyingPol['Action'] > 0:
            try:
                preparedAction = await ExecuteAction(reddit,Input['Id'],Input['Description'],ActionId,ApplyingPol['Message'])
            except:
                return [Message(False,False,MessageType.Text,f"Ocurrio un error al intentar borrar el post: {sys.exc_info()[1]}")]
            ActionDetailRow = preparedAction["ActionDetailRow"]
            modmail = preparedAction["ModMail"]
            sSubReddit = DB.GetSetting("subreddit")
            oSubReddit = await reddit.subreddit(sSubReddit)
            isMuted = False
            async for mutedUser in oSubReddit.muted():
                if mutedUser.name == ActionDetailRow['User']:
                    isMuted = True
                    MutedRelationship = mutedUser
            if isMuted:
                await oSubReddit.muted.remove(MutedRelationship)
            if ApplyingPol['Action'] == 1: #Warn
                objModmail = await oSubReddit.modmail.create(subject = f"Equipo de Moderacion de /r/{sSubReddit}",body = modmail, recipient = ActionDetailRow['User'],author_hidden = True)
                UpdateModmailId(objModmail.id, ActionId)
                await objModmail.archive()
            if ApplyingPol['Action'] == 2: #Ban
                sRet = await BanUser(oSubReddit,ApplyingPol['BanDays'],ActionDetailRow, modmail, ActionId)
                #lastMessages = await oSubReddit.modmail.conversations(sort="mod", state="archived", limit=1)
                async for lastMessage in oSubReddit.modmail.conversations(sort="mod", state="archived", limit=1):
                    #lastMessage.load()
                    if lastMessage.participant.name == ActionDetailRow['User']:
                         UpdateModmailId(lastMessage.id, ActionId)
                    else:
                        sRet += " - No se pudo enviar mod mail."
                return [Message(False,False,MessageType.Text,sRet)]
            if isMuted:
                await oSubReddit.muted.add(MutedRelationship)
            return [Message(False,False,MessageType.Text,"Usuario advertido.")]
            #Aca va la parte en donde vemos que hacemos con las politicas
        return [Message(False,False,MessageType.Text,"Error al buscar politica")]
    else:
        return [Message(False,False,MessageType.Text,"Formato incorrecto, por favor ingresa el motivo usando los IDs correspondientes")]

def UpdateModmailId(modmailId, ActionId):
    DB.WriteDB(f"UPDATE Actions SET modmailID = '{modmailId}' WHERE Id = {ActionId};")
async def ExecuteAction(reddit, InputId, InputDesc, ActionId, Message):
    ActionDetailRow = GetActionDetail('', ActionId,'')[0]
    LinkType = GetLinkType(f"https://{ActionDetailRow['Link']}")
    snapshot = None
    if LinkType == 1:
        submission = asyncpraw.models.Submission(reddit,url = f"https://{ActionDetailRow['Link']}")
        await submission.load()
    elif LinkType == 2:
        submission = asyncpraw.models.Comment(reddit,url = f"https://{ActionDetailRow['Link']}")
        await submission.load()
        AuxSubmission = submission
        snapshot = ""
        while type(AuxSubmission) == asyncpraw.models.reddit.comment.Comment:
            snapshot = f"[{datetime.fromtimestamp(AuxSubmission.created_utc).strftime('%Y-%m-%d %H:%M:%S')}] {GetAuthorName(AuxSubmission)}:\r\n\t{AuxSubmission.body}\r\n{snapshot}"
            AuxSubmission = await AuxSubmission.parent()
            await AuxSubmission.load()
    if LinkType != 0:
        await RemoveSubAndChildren(submission)
    UpdateQuery = f"UPDATE Actions SET ActionType = ?, Description = ?"
    if snapshot is not None:
        UpdateQuery = f"{UpdateQuery}, Snapshot = ?"
        params = (InputId,InputDesc,snapshot,ActionId)
    else:
        params = (InputId,InputDesc,ActionId)
    UpdateQuery = f"{UpdateQuery} WHERE Id = ?;"
    DB.WriteDB(UpdateQuery, params)
    ActionDetailRow = GetActionDetail('', ActionId,'')[0]
    modmail = await CreateModMail(Message, ActionDetailRow['Link'],ActionDetailRow['TypeDesc'],ActionDetailRow['Details'],ActionDetailRow['User'], reddit)
    return {'ActionDetailRow': ActionDetailRow, 'ModMail': modmail}
async def RemoveSubAndChildren(submission):
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
async def BanUser(sub,BanDays,ActionDetailRow, modmail, ActionId):
    try:
        if int(BanDays) > 0:
            await sub.banned.add(ActionDetailRow['User'],ban_reason=ActionDetailRow['TypeDesc'], duration=int(BanDays), ban_message=modmail)
            return f"Usuario banneado por {BanDays} dias."
        await sub.banned.add(ActionDetailRow['User'],ban_reason=ActionDetailRow['TypeDesc'], ban_message=modmail)
        return f"Usuario banneado permanentemente."
    except: 
        #unwarn ActionId rollback
        Unwarn(f"{ActionId}")
        return f"Ocurrio un error al intentar bannear al usuario: {sys.exc_info()[1]}"
def GetAuthorName(submission):
    if submission is not None and submission.author is not None:
        return submission.author.name
    return "[Usuario Eliminado]"
def GetActionDetail(Link, ActionId, User):
    sQuery = f"SELECT ifnull(m.RedditName,'Deleted Mod Id ' + a.Mod), ifnull(t.Description,'Deleted Reason Id ' + a.ActionType), ifnull(NULLIF(a.Description, ''), ifnull(t.DefaultMessage,'')), a.Date, a.Link, a.User, a.Id, t.Weight,  '<@' ||  m.DiscordID ||  '>', a.Snapshot FROM Actions a left join Moderators m on m.Id = a.Mod left join ActionType t on t.Id = a.ActionType "
    if ActionId > 0:
        sQuery = sQuery + f"WHERE a.Id = '{ActionId}'"
    elif len(Link) > 0:
        sQuery = sQuery + f"WHERE a.Link = '{SanatizeRedditLink(Link)}'"
    elif len(User) > 0:
        sQuery = sQuery + f"WHERE lower(a.User) = '{User.lower()}'"
    rows = DB.ExecuteDB(sQuery)
    lst = []
    for row in rows:
        lst.append({'ModName':row[0], 'TypeDesc': row[1], 'Details':row[2], 'Date':row[3], 'Link':row[4], 'User':row[5], 'Id': row[6], 'Weight': row[7], 'DiscordId': row[8], 'Snapshot':row[9]})
    return lst

async def InitAction(Link, reddit, SenderAction):
    try:
        linkType = GetLinkType(Link)
        if linkType > 0:
            if linkType == 3:  #Modmail
                oSub = await reddit.subreddit(DB.GetSetting("subreddit"))
                modmail = await oSub.modmail(SanatizeRedditLink(Link).rsplit('/',1)[1])
                AuthorName = modmail.participant.name  # This returns a ``Redditor`` object.
                Link = f"reddit.com/message/messages/{modmail.legacy_first_message_id}"
            rows = GetActionDetail(Link, 0,'')
            if len(rows) > 0:
                if rows[0]['TypeDesc'] is None:
                    return [Message(False,True,MessageType.Text,f"Ese link esta a la espera de que el Moderador {rows[0]['DiscordId']} elija el motivo de la sancion.")]
                return [Message(False,False,MessageType.Text,f"Ese link ya fue sancionado por Mod: {rows[0]['ModName']} \nFecha: {rows[0]['Date']} \nMotivo: {rows[0]['TypeDesc']}\nDetalles: {rows[0]['Details']}")]
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
                    row = (AuthorName, SanatizeRedditLink(Link), SenderAction['modID'],datetime.now() )
                    msgRetu = GetWarns(AuthorName, True)
                    DB.WriteDB("""INSERT INTO Actions (User, Link, Mod, Date) VALUES (?,?,?,?);""", row)
                    msgRetu.append(Message(False,False,MessageType.Text,f"Selecciona un motivo #<Id>, <Descripcion (Opcional)> \n{GetActionTypes(AuthorName)}\nUndo - Deshacer warn."))
                return msgRetu
        return []
    except:
        return [Message(False,False,MessageType.Text,f"Error al intentar iniciar la accion: {sys.exc_info()[1]}")]
client.run(TOKEN)