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
async def CheckModmail():
    while True:
        try:
            seconds = int(GetSetting(con,"RefreshModMail"))
            if seconds > 0:
                await asyncio.sleep(seconds)
            #get all new modmails
            #search for their IDs on DB where  db.modmailID = ID and db.LastUpdated < last_user_update
            #foreach
            #   send discord message @discordmod with the mod mail link and the reddit message/post link
            #   update db record LastUpdated =  last_user_update
            #unreadMail = await reddit.subreddit(GetSetting(con,"subreddit")).modmail.conversations(sort="unread")
            sQuery = ""
            #print(f"Unread Mail:\n")
            sub = await reddit.subreddit(GetSetting(con,"subreddit"))
            async for mail in sub.modmail.conversations(sort="unread"):
                #print(f"Mail Id: {mail.id}\tLast User Update: {mail.last_user_update}\n")
                sQuery += f" or (a.modmailID = '{mail.id}' and ifnull(a.LastModmailUpdated,'{mail.last_user_update}')  <= '{mail.last_user_update}')"
            cur = con.cursor()
            sQuery = f"select a.User, '<@' ||  m.DiscordID ||  '>', 'https://mod.reddit.com/mail/inbox/'|| a.modmailID,'https://'|| a.Link, at.Description, a.Id, a.LastModmailUpdated from Actions a join Moderators m on m.Id = a.Mod join ActionType at on at.Id = a.ActionType where {sQuery[4:]}"
            cur.execute(sQuery)
            rows = cur.fetchall()
            #print(f"Query: '{sQuery}'\nDB Matches: {len(rows)}\n")
            if len(rows) > 0:
                channel = client.get_channel(int(GetSetting(con,"GaryChannel")))
            for row in rows:
                #print(f"{row[1]}: {row[0]} Respondio al modmail generado por:\n{row[3]}\nSancion: {row[4]}\nClickea en el siguiente link para responder\n{row[2]}\nLastModmailUpdated: {row[6]}\nQuery criteria: [{sQuery}")
                embMsg = discord.Embed()
                embMsg.description = f"[u/{row[0]}](https://www.reddit.com/user/{row[0]}/) Respondio al modmail generado por:\n[{row[4]}]({row[3]})\nClickea [Aqui]({row[2]}) para responder"
                sentMsg = await channel.send(row[1], embed=embMsg)
                #await channel.send(f"{row[1]}: [u/{row[0]}](https://www.reddit.com/user/{row[0]}/) Respondio al modmail generado por:\n[{row[4]}]({row[3]})\nClickea [Aqui]({row[2]}) para responder")
                #await client.send_message(discord.Object(id=GetSetting(con,"GaryChannel")),f"{row[1]}: {row[0]} Respondio al modmail generado por:\n{row[3]}\nSancion: {row[4]}\nClickea en el siguiente link para responder\n{row[2]}")
                con.execute(f"Update Actions set LastModmailUpdated = '{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f+00:00')}' WHERE Id = {row[5]}")
                con.commit()
        except:
            print(f"Ocurrio un error al intentar obtener modmails de la API de Reddit: {sys.exc_info()[1]}")

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
client = discord.Client()
con = sl.connect(os.getenv('DB'),15)
rres = async_get_reddit_object()
if rres['status'] == 'success':
    reddit = rres['data']
else:
    print(rres['data'])


@client.event
async def on_ready():
    print(f'{client.user.name} has connected to Discord!')
    await CheckModmail()
    loop = asyncio.get_event_loop()
    loop.run_forever()

@client.event
async def on_message(message):
    Response = None
    if message.author == client.user:
        return
    SenderAction = CheckSender(con,message.author)
    if SenderAction['modID'] != '0': 
        StandardMessage = message.content.lower()
        if StandardMessage.strip(' ')=="gary":
            Response = [Message(False,False,MessageType.Text,"gary - Muestra esta ayuda\nwarns <user> - Muestra los warns de un usuario\nunwarn <id> - Elimina un warn especifico\nunban <user> - desbannea a un usuario\napproveuser <user> - Agrega a un usuario a la lista de usuarios aprobados\nmods - funciones de moderador\nsettings - configura las preferencias\npolicies - configura las politicas de moderacion\nreasons - configura los motivos de sancion\nstats - Muestra estadisticas de moderacion\n<link> - inicia el proceso de warn")]
        elif StandardMessage.startswith('warns '):
            Response = GetWarns(con,message.content[6:].strip(' '))
        elif StandardMessage.startswith('unwarn '):
            Response = Unwarn(con,message.content[7:].strip(' '))
        elif StandardMessage.startswith('unban '):
            Response = await Unban(message.content[6:].strip(' '), reddit,con)
        elif StandardMessage.startswith('approveuser '):
            Response = await ApproveUser(message.content[11:].strip(' '), reddit,con)
        elif StandardMessage.startswith('mods'):
            #MassSanatizeLinks(con) this is here if we need to run a mass sanatization if reddit changes the URL formats or something
            Response = HandleMods(con,message.content[5:].strip(' '))
        elif StandardMessage.startswith('settings'):
            Response = HandleSettings(con,message.content[9:].strip(' '))
        elif StandardMessage.startswith('policies'):
            Response = HandlePolicies(con,message.content[9:].strip(' '))
        elif StandardMessage.startswith('reasons'):
            Response = HandleReasons(con,message.content[8:].strip(' '))
        elif StandardMessage.startswith('stats'):
            Response = await HandleStats(con,message.content[6:].strip(' '), SenderAction['modID'], reddit)
        elif StandardMessage.strip(' ')=="undo":
            if SenderAction['status'] > 0:
                DeletePending(con,SenderAction['status'])
                Response = [Message(False,False,MessageType.Text,f"WarnID {SenderAction['status']} pendiente eliminado.")]
            else:
                Response = [Message(False,False,MessageType.Text,"No hay warnings pendientes.")]
        else:
            if SenderAction['status'] == 0:
                Response = await InitAction(message.content, con, reddit, SenderAction)
            else:
                linkType = GetLinkType(message.content,con)
                if linkType != 0:
                    DeletePending(con,SenderAction['status']) #el mod mando otro link en vez de responder, borrar lo pendiente y hacer uno nuevo
                    Response = await InitAction(message.content, con, reddit, SenderAction)
                else:
                    Response = await ResolveAction(con, message.content, SenderAction['status'], reddit)
        con.commit()
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
    seconds = int(GetSetting(con,"DelMsgAfterSeconds"))
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
def MassSanatizeLinks(con):
    cur = con.cursor()
    cur.execute(f"SELECT Id, Link FROM Actions")
    rows = cur.fetchall()
    sSub = GetSetting(con,"subreddit").lower()
    for row in rows:
        con.execute(f"Update Actions set [Link] = '{SanatizeRedditLinkSub(row[1], sSub)}' WHERE Id = {row[0]}")
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

def SanatizeRedditLink(sIn,con):
    return SanatizeRedditLinkSub(sIn, GetSetting(con,"subreddit").lower())   
def HandleReasons(con,sCommand):
    if sCommand.lower().startswith('list'):
        return GetReasons(con)
    if sCommand.lower().startswith('edit '):
        return EditReason(con,sCommand[4:].strip(' '))
    if sCommand.lower().startswith('remove '):
        return RemoveReason(con, sCommand[6:].strip(' '))
    if sCommand.lower().startswith('setdefaultmessage '):
        return DefaultMessageReason(con, sCommand[17:].strip(' '))
    else:
        return [Message(False,False,MessageType.Text,"reasons list - Muestra un listado de los motivos\nreasons remove <id> - Elimina un motivo\nreasons edit <id (entero, si esta vacio es un nuevo registro)>,<Descripcion(texto)>,<Peso(entero)> - Agrega o edita un motivo\nreasons setdefaultmessage <id (entero)>,<Descripcion(texto)> - Agrega (o quita si esta vacio) un mensaje por defecto a los motivos")]
def DefaultMessageReason(con, sCommand):
    sCommand = sCommand.replace("\,","[Coma]")
    sParams = sCommand.split(',')
    if len(sParams) == 2 and check_int(sParams[0].strip(' ')):
        sId = sParams[0].strip(' ')
        sDescription = sParams[1].replace("[Coma]",",").strip(' ')
        con.execute(f"Update ActionType set [DefaultMessage] = '{sDescription}' where Id = {sId}",row)
        return [Message(False,False,MessageType.Text,"Motivo agregado")]
    return [Message(False,False,MessageType.Text,f"Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\n<id(entero)>,<Mensaje(texto)>\nPara insertar comas [,] en los campos de texto usar el caracter de escape \\\,")]
def EditReason(con, sCommand):
    sCommand = sCommand.replace("\,","[Coma]")
    sParams = sCommand.split(',')
    if len(sParams) == 3:
        if (len(sParams[0].strip(' ')) == 0 or check_int(sParams[0].strip(' '))) and len(sParams[1].strip(' ')) > 0 and check_int(sParams[2].strip(' ')):
            sId = sParams[0].strip(' ')
            sDescription = sParams[1].replace("[Coma]",",")
            Weight = sParams[2].strip(' ')
            row = (sDescription,Weight)
            if len(sId) == 0: #Agregar Motivo
                con.execute(f"""INSERT INTO ActionType ([Description], [Weight], Active) VALUES (?,?,1);""",row)
                return [Message(False,False,MessageType.Text,"Motivo agregado")]
            else: # Editar Motivo
                cur = con.cursor()
                cur.execute(f"SELECT * FROM ActionType where Id = {sId} and Active = 1")
                rows = cur.fetchall()
                if len(rows) > 0:
                    con.execute(f"Update ActionType set [Description] = ?, [Weight] = ? WHERE Id = {sId}", row)
                    return [Message(False,False,MessageType.Text,f"Motivo #{sId} actualizado.")]
                return [Message(False,False,MessageType.Text,f"Motivo #{sId} no encontrado.")]
    return [Message(False,False,MessageType.Text,f"Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\n<id(entero, si esta vacio es un nuevo registro)>,<Descripcion(texto)>,<Peso(entero)>\nPara insertar comas [,] en los campos de texto usar el caracter de escape \\\,")]
def RemoveReason(con,sId):
    if not check_int(sId):
        return [Message(False,False,MessageType.Text,"Id Incorrecto")]
    iId = int(sId)
    cur = con.cursor()
    cur.execute(f"SELECT * FROM ActionType where Id = {iId}")
    rows = cur.fetchall()
    if len(rows) > 0:
        con.execute(f"Update ActionType set Active = 0 WHERE Id = {iId}")
        return [Message(False,False,MessageType.Text,f"Motivo #{iId} eliminado.")]
    return [Message(False,False,MessageType.Text,f"Motivo #{iId} no encontrado.")]
def GetReasons(con):
    cur = con.cursor()
    cur.execute(f"SELECT * FROM ActionType where Active = 1")
    rows = cur.fetchall()
    sRetu = ""
    for row in rows:
        sRetu = sRetu + f"Id: {row[0]}\nDescription: {row[1]}\nPeso: {row[2]}\n--------------------\n"
    return [Message(False,False,MessageType.Text,sRetu)]
async def HandleStats(con,sCommand, ModId, reddit):
    if sCommand.lower().startswith('mods'):
        return HandleModStats(con,sCommand[5:].strip(' '), ModId)
    if sCommand.lower().startswith('users'):
        return await HandleUserStats(con,sCommand[6:].strip(' '), reddit)
    if sCommand.lower().startswith('sub'):
        return HandleSubStats(con,sCommand[4:].strip(' '), ModId)
    else:
        return [Message(False,False,MessageType.Text,"stats mods (<mod name>)- Muestra estadisticas de los moderadores, puede filtrar por moderador individualmente\nstats users - Muestra estadisticas de los usuarios\nstats sub - Muestra estadisticas del subreddit")]
def SetPlotAsDates(filename):
    ax = plt.subplots()[1]
    fmt_day = mdates.DayLocator(interval = 5)
    ax.xaxis.set_major_locator(fmt_day)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
    ax.format_xdata = mdates.DateFormatter('%d/%m')
def CreateLinePlot(con, query,filename,xlabel, ylabel, title, new = True, lineLabel = '', fill= False, isXDateFormat = ''):
    cur = con.cursor()
    cur.execute(query)
    rows = cur.fetchall()
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
def HandleModStats(con,sCommand, ModID):
    msgRetu = []
    if len(sCommand) > 0:
        sCommand = sCommand.lower()
        msgRetu.append(Message(False,False,MessageType.Text,f"**Estadisticas del mod {sCommand}**\n" + GetTable(con,f"Select at.Description as Motivo, count(1) as Cantidad from Actions A join Moderators M on M.Id = A.Mod join ActionType AT on A.ActionType = AT.Id Where lower(M.Name) = '{sCommand}' group by at.Description order by Cantidad desc")))
        plot = GetModYearLog(con, sCommand,'plot.png')
        if len(plot) > 0:
            msgRetu.append(Message(False,False,MessageType.Image,plot))
        plot = GetModMonthLog(con, sCommand,'plotm.png')
        if len(plot) > 0:
            msgRetu.append(Message(False,False,MessageType.Image,plot))
        plot = GetModHourLog(con, sCommand,'ploth.png', ModID)
        if len(plot) > 0:
            msgRetu.append(Message(False,False,MessageType.Image,plot))
    else:
        msgRetu.append(Message(False,False,MessageType.Text,"**Estadisticas de Moderadores**\n" + GetTable(con,"select t1.Moderador, t1.Cantidad, t2.Puntos, printf(\"%.2f\", t2.Puntos*1.0 / t1.Cantidad*1.0) as PuntosPorAccion from  (select m.Name as Moderador, count(1) as Cantidad from Actions A join Moderators M on M.Id = A.Mod group by m.Name) t1 join (select m.Name as Moderador, sum(AT.Weight) as Puntos from Actions A join ActionType AT on A.ActionType = AT.Id join Moderators M on M.Id = A.Mod group by m.Name) t2 on t2.Moderador =t1.Moderador order by PuntosPorAccion desc") + "\n\n"))
    return msgRetu
def GetModYearLog(con, sCommand, pltName, lineLabel = '', new = True):
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
        return CreateLinePlot(con,sQuery,pltName, 'Mes', 'Cantidad de Acciones', 'Acciones por Mes', new, lineLabel)
    CreateLinePlot(con,sQuery,pltName, 'Mes', 'Cantidad de Acciones', 'Acciones por Mes', new,lineLabel = "Aprobados",fill = True)
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
    return CreateLinePlot(con,sQuery,pltName, 'Mes', 'Cantidad de Acciones', 'Acciones por Mes', False, lineLabel = "Removidos",fill = True)
def GetModMonthLog(con, sCommand, pltName, lineLabel = '', new = True):
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
        return CreateLinePlot(con,sQuery,pltName, 'Dia', 'Cantidad de Acciones', 'Acciones por Dia', new, lineLabel,isXDateFormat="%Y-%m-%d")
    CreateLinePlot(con,sQuery,pltName, 'Dia', 'Cantidad de Acciones', 'Acciones por Dia', new,lineLabel = "Aprobados",fill = True,isXDateFormat="%Y-%m-%d")
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
    sRet = CreateLinePlot(con,sQuery,pltName, 'Dia', 'Cantidad de Acciones', 'Acciones por Dia', False, lineLabel = "Removidos",fill = True,isXDateFormat="%Y-%m-%d")
    ax.format_xdata = mdates.DateFormatter('%d/%m')
    fig.autofmt_xdate()
    plt.savefig(pltName)
    return sRet
def GetModHourLog(con, sCommand, pltName, ModId, lineLabel = '', new = True):
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
    
    return CreateLinePlot(con,sQuery,pltName, 'Hora', 'Cantidad de Acciones', 'Acciones por Hora', new,lineLabel)
        #cantidad de acciones por mod
        #suma de pesos de acciones por mod
        # Horas de actividad
        #<Modname> Stats del mod
            #horas de actividad
            #dias de la semana
            #cantidad por dia (grafico?)
async def HandleUserStats(con,sCommand, reddit):
    #top users con mas medidas
    #top users con mas peso
    #porcentaje de users que responde a modmail
    if len(sCommand) > 0:
        return await HandleIndUserStats(con, reddit, sCommand)
    Limite = 20
    if check_int(sCommand):
        Limite = int(sCommand)
    sRetu = [Message(False,False,MessageType.Text,f"**Top {str(Limite)} usuarios con mas acciones**\n" + GetTable(con,f"select User, count(1) as Cantidad from Actions group by User order by Cantidad desc LIMIT {Limite}"))]
    sRetu.append(Message(False,False,MessageType.Text, f"**Cantidad de usuarios por cantidad de acciones**\n" + GetTable(con,f"Select Cantidad as CantidadDeFaltas, count(User) as Usuarios from (select A.User, count(1) as cantidad from Actions A join ActionType AT on AT.Id = A.ActionType where AT.Weight > 0 group by A.User) as Users group by Cantidad")))
    return sRetu
async def HandleIndUserStats(con, reddit, sCommand):
    oUser = await reddit.redditor(sCommand)
    sSubreddit = GetSetting(con,"subreddit").lower()
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
    MsgsRetu = GetWarns(con,sCommand, True)
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
def HandleSubStats(con,sCommand, ModId):
    sRetu = [Message(False,False,MessageType.Text,f"**Modmail**\n" + GetTable(con,f"select a1.Enviados, a2.Respondidos, printf(\"%.2f\",(100.00*a2.Respondidos)/a1.Enviados) as PorcentajeRespondidos from (select count(1) as Enviados,'a' as a from actions where Modmailid is not null) a1 join (select count(1) as Respondidos ,'a' as a from actions where lastmodmailupdated  is not null) a2 on a1.a = a2.a"))]
    sRetu.append(Message(False,False,MessageType.Text, f"**Cantidad de Acciones tomadas**\n" + GetTable(con,f"select AT.Description as Descripcion, count(1) as Cantidad from Actions A join ActionType AT on AT.Id = A.ActionType group by AT.Description order by Cantidad desc")))
    #sRetu.append(Message(False,False,MessageType.Text, f"**Acciones por dia de la semana**\n" + GetTable(con,"select case DDW when '0' then 'Domingo' when '1' then 'Lunes' when '2' then 'Martes' when '3' then 'Miercoles' when '4' then 'Jueves' when '5' then 'Viernes' when '6' then 'Sabado' end as DiaDeLaSemana, Cantidad from (SELECT strftime('%w',Date) DDW, count(1) as Cantidad from actions group by DDW)") + "\n"))
    
    
    plot = CreateLinePlot(con,f"select count(1) as 'cnt', strftime(\"%m-%Y\", a.Date) as 'mes' from Actions A where a.Date > DATE(Date(),'-1 years') group by strftime(\"%m-%Y\", a.Date)",'plot.png', 'Mes', 'Cantidad de Medidas', 'Medidas por Mes')
    if len(plot) > 0:
        sRetu.append(Message(False,False,MessageType.Image,plot))

    plot = CreateLinePlot(con,f"select count(1) as 'cnt', strftime(\"%m-%Y\", a.Date) as 'mes' from Actions A join ActionType AT on AT.Id = A.ActionType where AT.Weight > 0 and a.Date > DATE(Date(),'-1 years') group by strftime(\"%m-%Y\", a.Date)",'plotp.png', 'Mes', 'Cantidad de Medidas', 'Medidas punitivas por Mes')
    if len(plot) > 0:
        sRetu.append(Message(False,False,MessageType.Image,plot))
    
    cur = con.cursor()
    cur.execute("SELECT Name FROM Moderators")
    rows = cur.fetchall()
    plt.clf()
    for row in rows:
        plot = GetModYearLog(con, row[0],'ploty.png',row[0], False)
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
    plot = CreateLinePlot(con,sQuery,'ploth.png', 'Mes', 'Cantidad de Acciones', 'Acciones por Hora')
    if len(plot) > 0:
        sRetu.append(Message(False,False,MessageType.Image,plot))
    
    plt.clf()
    cur.execute("SELECT Name FROM Moderators where Active = 1")
    rows = cur.fetchall()
    for row in rows:
        plot = GetModHourLog(con, row[0],'plotm.png', ModId,row[0], False)
    if len(plot) > 0:
        sRetu.append(Message(False,False,MessageType.Image,plot))
    
    return sRetu
def GetTable(con, sQuery):
    cur = con.cursor()
    cur.execute(sQuery)
    return GetTableFormat(cur)
def GetTableFormat(cur):
    rows = cur.fetchall()
    sRetu = ""
    ColLens = []
    if len(rows) > 0:
        #Get the max len of each column for format
        for colName in cur.description:
            ColLens.append(len(colName[0]))
        for row in rows:
            iAux = 0
            for col in row:
                if len(str(col)) > ColLens[iAux]:
                    ColLens[iAux] = len(str(col))
                iAux += 1
        iAux = 0
        for colName in cur.description:
            sRetu += colName[0].ljust(ColLens[iAux]) + "\t"
            iAux += 1
        sRetu = sRetu.rstrip("\t") + "\n"
        sRetu += ("~" * (len(sRetu)+(iAux * 2))) + "\n"
        for row in rows:
            iAux = 0
            for col in row:
                sRetu += str(col).ljust(ColLens[iAux]) + "\t"
                iAux += 1
            sRetu = sRetu.rstrip("\t") + "\n"
        sRetu = '```'+ sRetu.rstrip("\n") + '```'
    return sRetu
def HandlePolicies(con,sCommand):
    if sCommand.lower().startswith('list'):
        return GetPolicies(con)
    if sCommand.lower().startswith('edit '):
        return EditPol(con,sCommand[4:].strip(' '))
    if sCommand.lower().startswith('remove '):
        return RemovePol(con, sCommand[7:].strip(' '))
    else:
        return [Message(False,False,MessageType.Text,"policies list - Muestra un listado de las politicas de moderacion\npolicies remove <id> - Elimina una politica de moderacion\npolicies edit <id(entero, si esta vacio es un nuevo registro)>,<From(entero)>,<To(entero)>,<Action(warn/ban)>,<BanDays(entero, si esta vacio es permanente)>,<Message(modmail)> - Agrega o edita una politica de moderacion")]
def EditPol(con, sCommand):
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
                con.execute(f"""INSERT INTO Policies ([From], [To], Action, BanDays, Message) VALUES (?,?,?,?,?);""",row)
                return [Message(False,False,MessageType.Text,"Politica agregada")]
            else: # Editar politica
                cur = con.cursor()
                cur.execute(f"SELECT * FROM Policies where Id = {sParams[0].strip(' ')}")
                rows = cur.fetchall()
                if len(rows) > 0:
                    con.execute(f"Update Policies set [From] = ?, [To] = ?, Action = ?, BanDays = ?, Message = ? WHERE Id = {sParams[0].strip(' ')}", row)
                    return [Message(False,False,MessageType.Text,f"Politica #{sParams[0].strip(' ')} actualizada.")]
                return [Message(False,False,MessageType.Text,f"Politica #{sParams[0].strip(' ')} no encontrada.")]
    return [Message(False,False,MessageType.Text,"Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\n<id(entero, si esta vacio es un nuevo registro)>,<From(entero)>,<To(entero)>,<Action(warn/ban)>,<BanDays(entero, si esta vacio es permanente)>,<Message(modmail)>\n\nReferencias a tener en cuenta al confeccionar el Mod Mail:\n[Sub] -> Nombre del subreddit a moderar\n[Link] -> Link sancionado\n[ActionTypeDesc] -> Por que fue sancionado el link\n[Details] -> Notas del moderador\n[Summary] -> Resumen de faltas\n\\n -> Nueva linea")]

def RemovePol(con,sId):
    if not check_int(sId):
        return [Message(False,False,MessageType.Text,"Id Incorrecto")]
    iId = int(sId)
    cur = con.cursor()
    cur.execute(f"SELECT * FROM Policies where Id = {iId}")
    rows = cur.fetchall()
    if len(rows) > 0:
        con.execute(f"DELETE FROM Policies WHERE Id = {iId}")
        return [Message(False,False,MessageType.Text,f"Politica #{iId} eliminada.")]
    return [Message(False,False,MessageType.Text,f"Politica #{iId} no encontrada.")]
def GetPolicies(con):
    cur = con.cursor()
    cur.execute(f"SELECT * FROM Policies")
    rows = cur.fetchall()
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
def GetLinkType(sIn,con):
    sIn = SanatizeRedditLink(sIn,con)
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
async def Unban(sUser, reddit,con):
    sub = await reddit.subreddit(GetSetting(con,"subreddit"))
    await sub.banned.remove(sUser)
    return [Message(False,False,MessageType.Text,f"Usuario {sUser} ha sido desbanneado.")]
async def ApproveUser(sUser, reddit,con):
    sub = await reddit.subreddit(GetSetting(con,"subreddit"))
    await sub.contributor.add(sUser)
    return [Message(False,False,MessageType.Text,f"Usuario {sUser} ha sido agregado a users aprobados.")]
def HandleMods(con,sCommand):
    if sCommand.lower().startswith('list'):
        return GetMods(con)
    if sCommand.lower().startswith('add '):
        return AddMod(con,sCommand[4:].strip(' '))
    if sCommand.lower().startswith('remove '):
        return RemoveMod(con, sCommand[7:].strip(' '))
    else:
        return [Message(False,False,MessageType.Text,"mods list - Muestra un listado de los moderadores\nmods add <nombre>,<nombre en reddit>,<ID de discord (numerico)> <Huso horario (numerico)> - Agrega un moderador\nmods remove <id> - Elimina un moderador por ID")]
def HandleSettings(con,sCommand):
    if sCommand.lower().startswith('list'):
        return GetSettings(con)
    if sCommand.lower().startswith('edit '):
        return EditSetting(con,sCommand[5:].strip(' '))
    else:
        return [Message(False,False,MessageType.Text,"settings list - Muestra un listado de preferencias\nsettings edit <setting> <value> - Edita una preferencia")]
def EditSetting(con, sCommand):
    chunks = sCommand.split(' ')
    if len(chunks) < 2:
        return [Message(False,False,MessageType.Text,"Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\nsettings edit <setting> <value>")]
    cur = con.cursor()
    cur.execute(f"SELECT * FROM Settings where [Key] = '{chunks[0].strip(' ')}'")
    rows = cur.fetchall()
    if len(rows) == 0:
        return [Message(False,False,MessageType.Text,"Preferencia no encontrada")]
    sValue = sCommand[len(chunks[0]):].strip(' ')
    if rows[0][3] == "int":
        if not check_int(sValue):
            return [Message(False,False,MessageType.Text,f"La preferencia {chunks[0]} debe ser un numero entero")]
    con.execute(f"UPDATE Settings SET [Value] = '{sValue}' WHERE Id = {rows[0][0]};")
    return [Message(False,False,MessageType.Text,f"La preferencia {chunks[0]} ha sido actualizada")]

def GetSetting(con,setting, ModId = 0):
    cur = con.cursor()
    cur.execute(f"SELECT [Value] FROM Settings where [Key] = '{setting}'")
    rows = cur.fetchall()
    return rows[0][0]

def check_int(s):
    if s is not None and len(str(s)) > 0:
        if str(s)[0] in ('-', '+'):
            return str(s)[1:].isdigit()
        return str(s).isdigit()
    return 0

def AddMod(con, sCommand):
    sParams = sCommand.split(',')
    if len(sParams) == 4:
        if sParams[2].strip(' ').isnumeric() and sParams[3].strip(' ').isnumeric() and len(sParams[0].strip(' ')) > 0 and len(sParams[1].strip(' ')) > 0:
            row = (sParams[0].strip(' '),sParams[1].strip(' '),sParams[2].strip(' '), sParams[3].strip(' '))
            con.execute(f"""INSERT INTO Moderators (Name, RedditName, DiscordID, TimeZone, Active) VALUES (?,?,?,?,1);""",row)
            return [Message(False,False,MessageType.Text,f"{sParams[0]} fue agregado a la lista de moderadores")]
    return [Message(False,False,MessageType.Text,"Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\n<nombre>,<nombre en reddit>,<ID de discord (numerico)>, <Huso Horario (numerico)>")]

def RemoveMod(con,sId):
    if not check_int(sId):
        return [Message(False,False,MessageType.Text,"Id Incorrecto")]
    iId = int(sId)
    cur = con.cursor()
    cur.execute(f"SELECT IsAdmin FROM Moderators where Id = {iId}")
    rows = cur.fetchall()
    if len(rows) > 0:
        if(rows[0][0] == 1):
            return [Message(False,False,MessageType.Text,"No podes remover a un administrador")]
        con.execute(f"Update Moderators set Active = false WHERE Id = {iId}")
        return [Message(False,False,MessageType.Text,f"Moderador #{iId} eliminado.")]
    return [Message(False,False,MessageType.Text,f"Moderador #{iId} no encontrado.")]

def GetMods(con):
    return [Message(False,False,MessageType.Text,GetTable(con, "SELECT Id, Name, RedditName, DiscordID, Active FROM Moderators"))]

def GetSettings(con):
    cur = con.cursor()
    cur.execute(f"SELECT * FROM Settings")
    rows = cur.fetchall()
    sRetu = ""
    for row in rows:
        sRetu = sRetu + f"Setting: {row[1]}\nValue: {row[2]}\n--------------------\n"
    return [Message(False,False,MessageType.Text,sRetu)]

def Unwarn(con,sId):
    if not sId.isnumeric():
        return [Message(False,False,MessageType.Text,"Id Incorrecto")]
    iId = int(sId)
    rows = GetActionDetail(con, '', iId,'')
    if len(rows) > 0:
        con.execute(f"DELETE FROM Actions WHERE Id = {iId}")
        return [Message(False,False,MessageType.Text,f"Warn #{iId} eliminado.")]
    return [Message(False,False,MessageType.Text,f"Warn #{iId} no encontrado.")]

def GetWarns(con,sUser, summary = False):
    rows = GetActionDetail(con, '', 0,sUser)
    sRetu = f"**Warns del usuario {sUser}**\n"
    dateFrom = datetime.now() - timedelta(days=int(GetSetting(con,"warnexpires")))
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
            sRetu += f"Warn Id: {row['Id']} \nMod: {row['ModName']} \nFecha: {row['Date']}\nActivo: {sActive}\n[{row['TypeDesc']}](https://{row['Link']})\nPuntos: {row['Weight']}\nDetalles: {row['Details']}\n--------------------\n"
    if len(sRetu) == 0:
        sRetu = f"No se encontaron warns para el usuario {sUser}"
    else:
        sRetu += f"Total: {iWeight} Puntos"
    return [Message(True,False,MessageType.Text,sRetu)]
def GetWarnsUserReport(con,sUser, msgLen):
    rows = GetActionDetail(con, '', 0,sUser)
    sRetu = ""
    dateFrom = datetime.now() - timedelta(days=int(GetSetting(con,"warnexpires")))
    iWeight = 0
    for row in rows:
        if datetime.strptime(row['Date'], '%Y-%m-%d %H:%M:%S.%f') >= dateFrom and row['Weight'] > 0:
            sRetu = sRetu + f"{row['Date'].split(' ')[0]}\t[{row['TypeDesc']}](https://{row['Link']})\tPuntos: {row['Weight']}\n\n"
            iWeight += row['Weight']
    sRetu = sRetu.rstrip("\n") + f" **<-- Nueva Falta**\n\n**Total**: {iWeight}"
    while len(sRetu) > msgLen:
        sRetu = sRetu[sRetu.find("\n") + 2:]
    return sRetu
def CheckSender(con, author):
    cur = con.cursor()
    cur.execute(f"SELECT Id FROM Moderators WHERE DiscordID = {author.id} and Active = true")
    rows = cur.fetchall()
    if len(rows) <= 0:
        return {'modID': '0', 'status': '0'} #not valid 
    modId = rows[0][0]
    cur.execute(f"SELECT Id FROM Actions WHERE Mod = {modId} and ActionType is null")
    rows = cur.fetchall()
    if len(rows) <= 0:
        return {'modID': modId, 'status': 0} #nothing pending
    else:
        return {'modID': modId, 'status': rows[0][0]} # Pending resolution

def GetActionTypes(con, UserName, filter = "", FormatTable = False):
    sRetu = ""
    Weight = GetUsersCurrentWeight(con,UserName)
    cur = con.cursor()
    cur.execute(f"SELECT '#' || t.Id as Id, t.Description as Descripcion, case t.Weight when 0 then 'Advertencia' else case p.Action when 1 then 'Advertencia' when 2 then case p.BanDays when -1 then 'Ban Permanente' else 'Ban ' || p.BanDays || ' Dias' End End End as Accion, t.Weight as Puntos FROM ActionType t join Policies p on p.[From] <= t.Weight + {Weight} and p.[To] >= t.Weight + {Weight} Where t.Active = 1 and t.Description like '%{filter}%' order by trim(t.Description), t.Weight desc")
    if FormatTable:
        return GetTableFormat(cur)
    rows = cur.fetchall()
    for row in rows:
        sRetu = f"{sRetu}{row[0]} - {row[1]} - **Puntos:** {row[3]} - **Accion: {row[2]} **\n"
    return sRetu

def DeletePending(con, Id):
    con.execute(f"DELETE FROM Actions WHERE Id = {Id}")

def ValidateActionType(con, Id):
    cur = con.cursor()
    cur.execute(f"SELECT Weight FROM ActionType WHERE Id = {Id} and Active = 1")
    rows = cur.fetchall()
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
def GetUsersCurrentWeight(con, sUser):
    dateFrom = datetime.now() - timedelta(days=int(GetSetting(con,"warnexpires")))
    cur = con.cursor()
    cur.execute(f"Select Sum(t.Weight) FROM Actions a Join ActionType t on t.Id = a.ActionType WHERE a.User = '{sUser}' and a.Date >= '{dateFrom}'")
    rows = cur.fetchall()
    if(len(rows)) > 0 and check_int(rows[0][0]):
        return int(rows[0][0])
    return 0
def GetApplyingPolicy(con, ActionId, AddedWeight):
    cur = con.cursor()
    cur.execute(f"Select User FROM Actions WHERE Id = {ActionId}")
    rows = cur.fetchall()
    if len(rows) > 0:
        if AddedWeight > 0:
            Weight = GetUsersCurrentWeight(con, rows[0][0]) + AddedWeight
        else:
            Weight = AddedWeight
        cur.execute(f"Select Action, BanDays, Message FROM Policies WHERE [From] <= {Weight} and [To] >= {Weight}")
        rows = cur.fetchall()
        if len(rows) > 0:
            return {'Action':rows[0][0], 'BanDays': rows[0][1], 'Message':rows[0][2]}
    return  {'Action':0, 'BanDays': '0', 'Message':'0'}

async def CreateModMail(sMessage, Link, ActionDesc, Details, sUser, con, reddit):
    sMessage = sMessage.replace("[Sub]", GetSetting(con,"subreddit"))
    sMessage = sMessage.replace("[Link]", f"https://{Link}")
    sMessage = sMessage.replace("[ActionTypeDesc]", ActionDesc)
    sMessage = sMessage.replace("[Details]", Details.replace("\n",">\n"))
    if "[Consultas]" in sMessage:
        sConsultas = await GetLastConsultasThread(con,reddit)
        sMessage = sMessage.replace("[Consultas]", sConsultas)
    if "[Summary]" in sMessage:
        sMessage = sMessage.replace("[Summary]", GetWarnsUserReport(con,sUser,1000- (len(sMessage) - len("[Summary]"))))
    sMessage = sMessage.replace("\\n", "\n")
    return sMessage[:1000]
async def GetLastConsultasThread(con,reddit):
    List = ""
    sub = await reddit.subreddit(GetSetting(con,"subreddit"))
    #Submissions = await reddit.subreddit(GetSetting(con,"subreddit")).search(query='author:AutoModerator AND (title:Consultas OR title:Preguntas)',sort='new',limit=1)
    async for Submission in sub.search(query='author:AutoModerator AND (title:Consultas OR title:Preguntas)',sort='new',limit=1):
        List += Submission.shortlink
    return List
def GetUserByID(con,ID):
    cur = con.cursor()
    cur.execute(f"SELECT [User] FROM Actions where [Id] = {ID}")
    rows = cur.fetchall()
    return rows[0][0]
async def ResolveAction(con, sIn, ActionId, reddit):
    if not sIn.startswith('#'):
        return [Message(False,False,MessageType.Text,f"Selecciona un motivo #<Id>, <Descripcion (Opcional)> \n{GetActionTypes(con,GetUserByID(con,ActionId),sIn.strip(' '))}\nUndo - Deshacer warn.")]
    Input = SanatizeInput(sIn)
    Weight = ValidateActionType(con, Input['Id'])
    if Weight > -1:
        ApplyingPol = GetApplyingPolicy(con,ActionId, Weight)
        if ApplyingPol['Action'] > 0:
            try:
                preparedAction = await PrepareAction(reddit,con,Input['Id'],Input['Description'],ActionId,ApplyingPol['Message'])
            except:
                return [Message(False,False,MessageType.Text,f"Ocurrio un error al intentar borrar el post: {sys.exc_info()[1]}")]
            ActionDetailRow = preparedAction["ActionDetailRow"]
            modmail = preparedAction["ModMail"]
            sSubReddit = GetSetting(con,"subreddit")
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
                UpdateModmailId(con,objModmail.id, ActionId)
                await objModmail.archive()
            if ApplyingPol['Action'] == 2: #Ban
                sRet = await BanUser(oSubReddit,ApplyingPol['BanDays'],ActionDetailRow, modmail, ActionId,con)
                #lastMessages = await oSubReddit.modmail.conversations(sort="mod", state="archived", limit=1)
                async for lastMessage in oSubReddit.modmail.conversations(sort="mod", state="archived", limit=1):
                    #lastMessage.load()
                    if lastMessage.participant.name == ActionDetailRow['User']:
                         UpdateModmailId(con,lastMessage.id, ActionId)
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

def UpdateModmailId(con, modmailId, ActionId):
    con.execute(f"UPDATE Actions SET modmailID = '{modmailId}' WHERE Id = {ActionId};")
async def PrepareAction(reddit, con, InputId, InputDesc, ActionId, Message):
    con.execute(f"UPDATE Actions SET ActionType = {InputId}, Description = '{InputDesc}' WHERE Id = {ActionId};")
    ActionDetailRows = GetActionDetail(con, '', ActionId,'')
    ActionDetailRow = ActionDetailRows[0]
    modmail = await CreateModMail(Message, ActionDetailRow['Link'],ActionDetailRow['TypeDesc'],ActionDetailRow['Details'],ActionDetailRow['User'],con, reddit)
    LinkType = GetLinkType(f"https://{ActionDetailRow['Link']}",con)
    if LinkType == 1:
        submission = asyncpraw.models.Submission(reddit,url = f"https://{ActionDetailRow['Link']}")
    elif LinkType == 2:
        submission = asyncpraw.models.Comment(reddit,url = f"https://{ActionDetailRow['Link']}")
    if LinkType != 0:
        await submission.load()
        await submission.mod.remove()
    return {'ActionDetailRow': ActionDetailRow, 'ModMail': modmail}

async def BanUser(sub,BanDays,ActionDetailRow, modmail, ActionId,con):
    try:
        if int(BanDays) > 0:
            await sub.banned.add(ActionDetailRow['User'],ban_reason=ActionDetailRow['TypeDesc'], duration=int(BanDays), ban_message=modmail)
            return f"Usuario banneado por {BanDays} dias."
        await sub.banned.add(ActionDetailRow['User'],ban_reason=ActionDetailRow['TypeDesc'], ban_message=modmail)
        return f"Usuario banneado permanentemente."
    except: 
        #unwarn ActionId rollback
        Unwarn(con,f"{ActionId}")
        return f"Ocurrio un error al intentar bannear al usuario: {sys.exc_info()[1]}"
def GetActionDetail(con, Link, ActionId, User):
    sQuery = f"SELECT ifnull(m.RedditName,'Deleted Mod Id ' + a.Mod), ifnull(t.Description,'Deleted Reason Id ' + a.ActionType), ifnull(NULLIF(a.Description, ''), ifnull(t.DefaultMessage,'')), a.Date, a.Link, a.User, a.Id, t.Weight,  '<@' ||  m.DiscordID ||  '>' FROM Actions a left join Moderators m on m.Id = a.Mod left join ActionType t on t.Id = a.ActionType "
    cur = con.cursor()
    if ActionId > 0:
        sQuery = sQuery + f"WHERE a.Id = '{ActionId}'"
    elif len(Link) > 0:
        sQuery = sQuery + f"WHERE a.Link = '{SanatizeRedditLink(Link,con)}'"
    elif len(User) > 0:
        sQuery = sQuery + f"WHERE lower(a.User) = '{User.lower()}'"
    cur.execute(sQuery)
    rows = cur.fetchall()
    lst = []
    for row in rows:
        lst.append({'ModName':row[0], 'TypeDesc': row[1], 'Details':row[2], 'Date':row[3], 'Link':row[4], 'User':row[5], 'Id': row[6], 'Weight': row[7], 'DiscordId': row[8]})
    return lst

async def InitAction(Link, con, reddit, SenderAction):
    try:
        linkType = GetLinkType(Link,con)
        if linkType > 0:
            if linkType == 3:  #Modmail
                oSub = await reddit.subreddit(GetSetting(con,"subreddit"))
                modmail = await oSub.modmail(SanatizeRedditLink(Link,con).rsplit('/',1)[1])
                AuthorName = modmail.participant.name  # This returns a ``Redditor`` object.
                Link = f"reddit.com/message/messages/{modmail.legacy_first_message_id}"
            rows = GetActionDetail(con, Link, 0,'')
            if len(rows) > 0:
                if rows[0]['TypeDesc'] is None:
                    return [Message(False,True,MessageType.Text,f"Ese link esta a la espera de que el Moderador {rows[0]['DiscordId']} elija el motivo de la sancion.")]
                return [Message(False,False,MessageType.Text,f"Ese link ya fue sancionado por Mod: {rows[0]['ModName']} \nFecha: {rows[0]['Date']} \nMotivo: {rows[0]['TypeDesc']}\nDetalles: {rows[0]['Details']}")]
            else:
                if linkType == 1:
                    submission = asyncpraw.models.Submission(reddit,url = Link)
                    await submission.load()
                    AuthorName = submission.author.name
                elif linkType == 2:
                    comment = asyncpraw.models.Comment(reddit,url = Link)
                    await comment.load()
                    AuthorName = comment.author.name  # This returns a ``Redditor`` object.
                row = (AuthorName, SanatizeRedditLink(Link,con), SenderAction['modID'],datetime.now() )
                msgRetu = GetWarns(con,AuthorName, True)
                con.execute("""INSERT INTO Actions (User, Link, Mod, Date) VALUES (?,?,?,?);""", row)
                msgRetu.append(Message(False,False,MessageType.Text,f"Selecciona un motivo #<Id>, <Descripcion (Opcional)> \n{GetActionTypes(con,AuthorName)}\nUndo - Deshacer warn."))
                return msgRetu
        return []
    except:
        return [Message(False,False,MessageType.Text,f"Error al intentar iniciar la accion: {sys.exc_info()[1]}")]
client.run(TOKEN)