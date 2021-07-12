# bot.py
import os
import sqlite3 as sl
import discord
import praw
import sys
import asyncio
import threading
from prawcore.exceptions import OAuthException, ResponseException
from dotenv import load_dotenv
from Reddit import get_reddit_object
from datetime import datetime
from datetime import timedelta, date
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
            unreadMail = reddit.subreddit(GetSetting(con,"subreddit")).modmail.conversations(sort="unread")
            sQuery = ""
            print(f"Unread Mail:\n")
            for mail in unreadMail:
                print(f"Mail Id: {mail.id}\tLast User Update: {mail.last_user_update}\n")
                sQuery += f" or (a.modmailID = '{mail.id}' and ifnull(a.LastModmailUpdated,'{mail.last_user_update}')  <= '{mail.last_user_update}')"
            cur = con.cursor()
            sQuery = f"select a.User, '<@' ||  m.DiscordID ||  '>', 'https://mod.reddit.com/mail/inbox/'|| a.modmailID,'https://'|| a.Link, at.Description, a.Id, a.LastModmailUpdated from Actions a join Moderators m on m.Id = a.Mod join ActionType at on at.Id = a.ActionType where {sQuery[4:]}"
            cur.execute(sQuery)
            rows = cur.fetchall()
            print(f"Query: '{sQuery}'\nDB Matches: {len(rows)}\n")
            if len(rows) > 0:
                channel = client.get_channel(int(GetSetting(con,"GaryChannel")))
            for row in rows:
                print(f"{row[1]}: {row[0]} Respondio al modmail generado por:\n{row[3]}\nSancion: {row[4]}\nClickea en el siguiente link para responder\n{row[2]}\nLastModmailUpdated: {row[6]}\nQuery criteria: [{sQuery}")
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
con = sl.connect(os.getenv('DB'))
rres = get_reddit_object()
if rres['status'] == 'success':
    reddit = rres['data']
else:
    print(rres['data'])


@client.event
async def on_ready():
    print(f'{client.user.name} has connected to Discord!')
    await CheckModmail()

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    SenderAction = CheckSender(con,message.author)
    if SenderAction['modID'] != '0':
        if message.content.lower().strip(' ')=="gary":
            Response = "gary - Muestra esta ayuda\nwarns <user> - Muestra los warns de un usuario\nunwarn <id> - Elimina un warn especifico\nunban <user> - desbannea a un usuario\nmods - funciones de moderador\nsettings - configura las preferencias\npolicies - configura las politicas de moderacion\nreasons - configura los motivos de sancion\nstats - Muestra estadisticas de moderacion\n<link> - inicia el proceso de warn"
        elif message.content.lower().startswith('warns '):
            Response = GetWarns(con,message.content[6:].strip(' '))
        elif message.content.lower().startswith('unwarn '):
            Response = Unwarn(con,message.content[7:].strip(' '))
        elif message.content.lower().startswith('unban '):
            Response = Unban(message.content[6:].strip(' '), reddit,con)
        elif message.content.lower().startswith('mods'):
            #MassSanatizeLinks(con) this is here if we need to run a mass sanatization if reddit changes the URL formats or something
            Response = HandleMods(con,message.content[5:].strip(' '))
        elif message.content.lower().startswith('settings'):
            Response = HandleSettings(con,message.content[9:].strip(' '))
        elif message.content.lower().startswith('policies'):
            Response = HandlePolicies(con,message.content[9:].strip(' '))
        elif message.content.lower().startswith('reasons'):
            Response = HandleReasons(con,message.content[8:].strip(' '))
        elif message.content.lower().startswith('stats'):
            Response = HandleStats(con,message.content[6:].strip(' '))
        else:
            if SenderAction['status'] == '0':
                Response = InitAction(message.content, con, reddit, SenderAction)
            else:
                linkType = GetLinkType(message.content,con)
                if linkType != 0:
                    DeletePending(con,SenderAction['status']) #el mod mando otro link en vez de responder, borrar lo pendiente y hacer uno nuevo
                    Response = InitAction(message.content, con, reddit, SenderAction)
                else:
                    Response = ResolveAction(con, message.content, SenderAction['status'], reddit)
        con.commit()
        if Response is not None:
            Msgs = []
            bNoDel = False
            if Response.startswith('[NoDel]'):
                bNoDel = True
                Response = Response[7:]
            bEmbed = False
            if Response.startswith('[Embed]'):
                bEmbed = True
                Response = Response[7:]
            for indRes in Sectionize(Response, "--------------------", True):
                if bEmbed:
                    embMsg = discord.Embed()
                    embMsg.description = indRes
                    sentMsg = await message.channel.send(embed=embMsg)
                else:
                    sentMsg = await message.channel.send(indRes)
                Msgs.append(sentMsg)
            seconds = int(GetSetting(con,"DelMsgAfterSeconds"))
            if seconds > 0 and not bNoDel:
                await asyncio.sleep(seconds)
                for Msg in Msgs:
                    await Msg.delete()

    if message.content == 'raise-exception':
        raise discord.DiscordException

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
    if sIn.startswith('reddit.com') and subReddit in sIn.lower():
        sIn.rstrip('/')
        chunks = sIn.split("?")
        afterlastslash = 0
        if(len(chunks) > 1):
            afterlastslash = len(chunks[len(chunks) -1]) + 1 
        if afterlastslash > 0:
            sIn = sIn[:afterlastslash * -1]
        sIn = sIn.rstrip('/')
        chunks = sIn.split('/')
        if len(chunks) == 7 or len(chunks) == 6:
            sIn = sIn.replace(chunks[5],"_")
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
        return RemoveReason(con, sCommand[7:].strip(' '))
    else:
        return "reasons list - Muestra un listado de los motivos\nreasons remove <id> - Elimina un motivo\nreasons edit <id(entero, si esta vacio es un nuevo registro)>,<Descripcion(texto)>,<Peso(entero)> - Agrega o edita un motivo"
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
                return "Motivo agregado"
            else: # Editar Motivo
                cur = con.cursor()
                cur.execute(f"SELECT * FROM ActionType where Id = {sId} and Active = 1")
                rows = cur.fetchall()
                if len(rows) > 0:
                    con.execute(f"Update ActionType set [Description] = ?, [Weight] = ? WHERE Id = {sId}", row)
                    return f"Motivo #{sId} actualizado."
                return f"Motivo #{sId} no encontrado."
    return f"Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\n<id(entero, si esta vacio es un nuevo registro)>,<Descripcion(texto)>,<Peso(entero)>\nPara insertar comas [,] en los campos de texto usar el caracter de escape \\\,"
def RemoveReason(con,sId):
    if not check_int(sId):
        return "Id Incorrecto"
    iId = int(sId)
    cur = con.cursor()
    cur.execute(f"SELECT * FROM ActionType where Id = {iId}")
    rows = cur.fetchall()
    if len(rows) > 0:
        con.execute(f"Update ActionType set Active = 0 WHERE Id = {iId}")
        return f"Motivo #{iId} eliminado."
    return f"Motivo #{iId} no encontrado."
def GetReasons(con):
    cur = con.cursor()
    cur.execute(f"SELECT * FROM ActionType where Active = 1")
    rows = cur.fetchall()
    sRetu = ""
    for row in rows:
        sRetu = sRetu + f"Id: {row[0]}\nDescription: {row[1]}\nPeso: {row[2]}\n--------------------\n"
    return sRetu
def HandleStats(con,sCommand):
    if sCommand.lower().startswith('mods'):
        return HandleModStats(con,sCommand[5:].strip(' '))
    if sCommand.lower().startswith('users'):
        return HandleUserStats(con,sCommand[6:].strip(' '))
    if sCommand.lower().startswith('sub'):
        return HandleSubStats(con,sCommand[4:].strip(' '))
    else:
        return "stats mods - Muestra estadisticas de los moderadores\nstats users - Muestra estadisticas de los usuarios\nstats sub - Muestra estadisticas del subreddit"
def HandleModStats(con,sCommand):
    sRetu = "**Estadisticas de Moderadores**\n" + GetTable(con,"select t1.Moderador, t1.Cantidad, t2.Puntos, printf(\"%.2f\", t2.Puntos*1.0 / t1.Cantidad*1.0) as PuntosPorAccion from  (select m.Name as Moderador, count(1) as Cantidad from Actions A join Moderators M on M.Id = A.Mod group by m.Name) t1 join (select m.Name as Moderador, sum(AT.Weight) as Puntos from Actions A join ActionType AT on A.ActionType = AT.Id join Moderators M on M.Id = A.Mod group by m.Name) t2 on t2.Moderador =t1.Moderador order by PuntosPorAccion desc") + "\n\n"
    return sRetu
        #cantidad de acciones por mod
        #suma de pesos de acciones por mod
        # Horas de actividad
        #<Modname> Stats del mod
            #horas de actividad
            #dias de la semana
            #cantidad por dia (grafico?)
def HandleUserStats(con,sCommand):
    #top users con mas medidas
    #top users con mas peso
    #porcentaje de users que responde a modmail
    Limite = 20
    if check_int(sCommand):
        Limite = int(sCommand)
    sRetu = f"**Top {str(Limite)} usuarios con mas acciones**\n" + GetTable(con,f"select User, count(1) as Cantidad from Actions group by User order by Cantidad desc LIMIT {Limite}") + "\n\n"
    return sRetu
def HandleSubStats(con,sCommand):
    sRetu = f"**Modmail**\n" + GetTable(con,f"select a1.Enviados, a2.Respondidos, printf(\"%.2f\",(100.00*a2.Respondidos)/a1.Enviados) as PorcentajeRespondidos from (select count(1) as Enviados,'a' as a from actions where Modmailid is not null) a1 join (select count(1) as Respondidos ,'a' as a from actions where lastmodmailupdated  is not null) a2 on a1.a = a2.a") + "\n"
    sRetu += f"**Cantidad de Acciones tomadas**\n" + GetTable(con,f"select AT.Description as Descripcion, count(1) as Cantidad from Actions A join ActionType AT on AT.Id = A.ActionType group by AT.Description order by Cantidad desc") + "\n"
    sRetu += f"**Acciones por dia de la semana**\n" + GetTable(con,"select case DDW when '0' then 'Domingo' when '1' then 'Lunes' when '2' then 'Martes' when '3' then 'Miercoles' when '4' then 'Jueves' when '5' then 'Viernes' when '6' then 'Sabado' end as DiaDeLaSemana, Cantidad from (SELECT strftime('%w',Date) DDW, count(1) as Cantidad from actions group by DDW)") + "\n"
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
        return "policies list - Muestra un listado de las politicas de moderacion\npolicies remove <id> - Elimina una politica de moderacion\npolicies edit <id(entero, si esta vacio es un nuevo registro)>,<From(entero)>,<To(entero)>,<Action(warn/ban)>,<BanDays(entero, si esta vacio es permanente)>,<Message(modmail)> - Agrega o edita una politica de moderacion"
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
                return "Politica agregada"
            else: # Editar politica
                cur = con.cursor()
                cur.execute(f"SELECT * FROM Policies where Id = {sParams[0].strip(' ')}")
                rows = cur.fetchall()
                if len(rows) > 0:
                    con.execute(f"Update Policies set [From] = ?, [To] = ?, Action = ?, BanDays = ?, Message = ? WHERE Id = {sParams[0].strip(' ')}", row)
                    return f"Politica #{sParams[0].strip(' ')} actualizada."
                return f"Politica #{sParams[0].strip(' ')} no encontrada."
    return "Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\n<id(entero, si esta vacio es un nuevo registro)>,<From(entero)>,<To(entero)>,<Action(warn/ban)>,<BanDays(entero, si esta vacio es permanente)>,<Message(modmail)>\n\nReferencias a tener en cuenta al confeccionar el Mod Mail:\n[Sub] -> Nombre del subreddit a moderar\n[Link] -> Link sancionado\n[ActionTypeDesc] -> Por que fue sancionado el link\n[Details] -> Notas del moderador\n[Summary] -> Resumen de faltas\n\\n -> Nueva linea"

def RemovePol(con,sId):
    if not check_int(sId):
        return "Id Incorrecto"
    iId = int(sId)
    cur = con.cursor()
    cur.execute(f"SELECT * FROM Policies where Id = {iId}")
    rows = cur.fetchall()
    if len(rows) > 0:
        con.execute(f"DELETE FROM Policies WHERE Id = {iId}")
        return f"Politica #{iId} eliminada."
    return f"Politica #{iId} no encontrada."
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
    return sRetu
def GetLinkType(sIn,con):
    sIn = SanatizeRedditLink(sIn,con)
    chunks = sIn.split('/')
    if len(chunks) == 0:
        return 0 #invalid link
    if len(chunks) == 6:
        return 1 #link/post
    if len(chunks) == 7:
        return 2 #comment
    return 0 
def Unban(sUser, reddit,con):
    sub = reddit.subreddit(GetSetting(con,"subreddit"))
    sub.banned.remove(sUser)
    return f"Usuario {sUser} ha sido desbanneado."
def HandleMods(con,sCommand):
    if sCommand.lower().startswith('list'):
        return GetMods(con)
    if sCommand.lower().startswith('add '):
        return AddMod(con,sCommand[4:].strip(' '))
    if sCommand.lower().startswith('remove '):
        return RemoveMod(con, sCommand[7:].strip(' '))
    else:
        return "mods list - Muestra un listado de los moderadores\nmods add <nombre>,<nombre en reddit>,<ID de discord (numerico)> - Agrega un moderador\nmods remove <id> - Elimina un moderador por ID"
def HandleSettings(con,sCommand):
    if sCommand.lower().startswith('list'):
        return GetSettings(con)
    if sCommand.lower().startswith('edit '):
        return EditSetting(con,sCommand[5:].strip(' '))
    else:
        return "settings list - Muestra un listado de preferencias\nsettings edit <setting> <value> - Edita una preferencia"
def EditSetting(con, sCommand):
    chunks = sCommand.split(' ')
    if len(chunks) < 2:
        return "Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\nsettings edit <setting> <value>"
    cur = con.cursor()
    cur.execute(f"SELECT * FROM Settings where [Key] = '{chunks[0].strip(' ')}'")
    rows = cur.fetchall()
    if len(rows) == 0:
        return "Preferencia no encontrada"
    sValue = sCommand[len(chunks[0]):].strip(' ')
    if rows[0][3] == "int":
        if not check_int(sValue):
            return f"La preferencia {chunks[0]} debe ser un numero entero"
    con.execute(f"UPDATE Settings SET [Value] = '{sValue}' WHERE Id = {rows[0][0]};")
    return f"La preferencia {chunks[0]} ha sido actualizada"

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
    if len(sParams) == 3:
        if sParams[2].strip(' ').isnumeric() and len(sParams[0].strip(' ')) > 0 and len(sParams[1].strip(' ')) > 0:
            row = (sParams[0].strip(' '),sParams[1].strip(' '),sParams[2].strip(' '))
            con.execute(f"""INSERT INTO Moderators (Name, RedditName, DiscordID) VALUES (?,?,?);""",row)
            return f"{sParams[0]} fue agregado a la lista de moderadores"
    return "Formato incorrecto, por favor asegurate de que todos los campos esten completados correctamente:\n<nombre>,<nombre en reddit>,<ID de discord (numerico)>"

def RemoveMod(con,sId):
    if not check_int(sId):
        return "Id Incorrecto"
    iId = int(sId)
    cur = con.cursor()
    cur.execute(f"SELECT IsAdmin FROM Moderators where Id = {iId}")
    rows = cur.fetchall()
    if len(rows) > 0:
        if(rows[0][0] == 1):
            return "No podes remover a un administrador"
        con.execute(f"DELETE FROM Moderators WHERE Id = {iId}")
        return f"Moderador #{iId} eliminado."
    return f"Moderador #{iId} no encontrado."

def GetMods(con):
    return GetTable(con, "SELECT Id, Name, RedditName, DiscordID FROM Moderators")
    cur = con.cursor()
    cur.execute(f"SELECT * FROM Moderators")
    rows = cur.fetchall()
    sRetu = ""
    for row in rows:
        sRetu = sRetu + f"Mod Id: {row[0]}\nName: {row[1]}\nReddit Name: {row[2]}\nDiscord Id: {row[3]}\n--------------------\n"
    return sRetu

def GetSettings(con):
    cur = con.cursor()
    cur.execute(f"SELECT * FROM Settings")
    rows = cur.fetchall()
    sRetu = ""
    for row in rows:
        sRetu = sRetu + f"Setting: {row[1]}\nValue: {row[2]}\n--------------------\n"
    return sRetu

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
    sRetu = '[Embed]'
    dateFrom = datetime.now() - timedelta(days=int(GetSetting(con,"warnexpires")))
    iWeight = 0
    for row in rows:
        if datetime.strptime(row['Date'], '%Y-%m-%d %H:%M:%S.%f') >= dateFrom:
            sActive = "Si"
            if not row['Weight'] is None:
                iWeight = iWeight + row['Weight']
        else:
            sActive = "No"
        
        #sRetu = sRetu + f"Warn Id: {row['Id']} \nMod: {row['ModName']} \nFecha: {row['Date']}\nActivo: {sActive}\nLink: {row['Link']}\nMotivo  : {row['TypeDesc']}\nPuntos: {row['Weight']}\nDetalles: {row['Details']}\n--------------------\n"
        sRetu = sRetu + f"Warn Id: {row['Id']} \nMod: {row['ModName']} \nFecha: {row['Date']}\nActivo: {sActive}\n[{row['TypeDesc']}](https://{row['Link']})\nPuntos: {row['Weight']}\nDetalles: {row['Details']}\n--------------------\n"
    if len(sRetu) == 0:
        sRetu = f"No se encontaron warns para el usuario {sUser}"
    else:
        sRetu = sRetu + f"Total: {iWeight} Puntos"
    return sRetu
def GetWarnsUserReport(con,sUser, msgLen):

    rows = GetActionDetail(con, '', 0,sUser)
    sRetu = ""
    dateFrom = datetime.now() - timedelta(days=int(GetSetting(con,"warnexpires")))
    iWeight = 0
    for row in rows:
        if datetime.strptime(row['Date'], '%Y-%m-%d %H:%M:%S.%f') >= dateFrom:
            sRetu = sRetu + f"{row['Date'].split(' ')[0]}\t[{row['TypeDesc']}](https://{row['Link']})\tPuntos: {row['Weight']}\n\n"
            iWeight += row['Weight']
    sRetu = sRetu.rstrip("\n") + f" **<-- Nueva Falta**\n\n**Total**: {iWeight}"
    while len(sRetu) > msgLen:
        sRetu = sRetu[sRetu.find("\n") + 2:]
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

def GetActionTypes(con, UserName, FormatTable = False):
    sRetu = ""
    Weight = GetUsersCurrentWeight(con,UserName)
    cur = con.cursor()
    cur.execute(f"SELECT '#' || t.Id as Id, t.Description as Descripcion, case t.Weight when 0 then 'Advertencia' else case p.Action when 1 then 'Advertencia' when 2 then case p.BanDays when -1 then 'Ban Permanente' else 'Ban ' || p.BanDays || ' Dias' End End End as Accion, t.Weight as Puntos FROM ActionType t join Policies p on p.[From] <= t.Weight + {Weight} and p.[To] >= t.Weight + {Weight} Where t.Active = 1 order by trim(t.Description), t.Weight desc")
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
    return  {'Action':'0', 'BanDays': '0', 'Message':'0'}

def CreateModMail(sMessage, Link, ActionDesc, Details, sUser, con):
    sMessage = sMessage.replace("[Sub]", GetSetting(con,"subreddit"))
    sMessage = sMessage.replace("[Link]", f"https://{Link}")
    sMessage = sMessage.replace("[ActionTypeDesc]", ActionDesc)
    sMessage = sMessage.replace("[Details]", Details.replace("\n",">\n"))
    if "[Summary]" in sMessage:
        sMessage = sMessage.replace("[Summary]", GetWarnsUserReport(con,sUser,1000- (len(sMessage) - len("[Summary]"))))
    sMessage = sMessage.replace("\\n", "\n")
    return sMessage[:1000]

def ResolveAction(con, sIn, ActionId, reddit):
    if not sIn.startswith('#'):
        return None
    Input = SanatizeInput(sIn)
    Weight = ValidateActionType(con, Input['Id'])
    if Weight > -1:
        ApplyingPol = GetApplyingPolicy(con,ActionId, Weight)
        if ApplyingPol['Action'] > 0:
            try:
                preparedAction = PrepareAction(reddit,con,Input['Id'],Input['Description'],ActionId,ApplyingPol['Message'])
            except:
                return f"Ocurrio un error al intentar borrar el post: {sys.exc_info()[1]}"
            ActionDetailRow = preparedAction["ActionDetailRow"]
            modmail = preparedAction["ModMail"]
            sSubReddit = GetSetting(con,"subreddit")
            isMuted = False
            for mutedUser in reddit.subreddit(sSubReddit).muted():
                if mutedUser.name == ActionDetailRow['User']:
                    isMuted = True
                    MutedRelationship = mutedUser
            if isMuted:
                reddit.subreddit(sSubReddit).muted.remove(MutedRelationship)
            if ApplyingPol['Action'] == 1: #Warn
                objModmail = reddit.subreddit(sSubReddit).modmail.create(subject = f"Equipo de Moderacion de /r/{sSubReddit}",body = modmail, recipient = ActionDetailRow['User'],author_hidden = True)
                reddit.subreddit(sSubReddit)
                UpdateModmailId(con,objModmail.id, ActionId)
                objModmail.archive()
            if ApplyingPol['Action'] == 2: #Ban
                sRet = BanUser(reddit,sSubReddit,ApplyingPol['BanDays'],ActionDetailRow, modmail, ActionId,con)
                lastMessages = reddit.subreddit(sSubReddit).modmail.conversations(sort="mod", state="archived", limit=1)
                for lastMessage in lastMessages:
                    if lastMessage.user.name == ActionDetailRow['User']:
                         UpdateModmailId(con,lastMessage.id, ActionId)
                    else:
                        sRet += " - No se pudo enviar mod mail."
                return sRet
            if isMuted:
                reddit.subreddit(sSubReddit).muted.add(MutedRelationship)
            return "Usuario advertido."
            #Aca va la parte en donde vemos que hacemos con las politicas
        return "Error al buscar politica"
    else:
        return "Formato incorrecto, por favor ingresa el motivo usando los IDs correspondientes"

def UpdateModmailId(con, modmailId, ActionId):
    con.execute(f"UPDATE Actions SET modmailID = '{modmailId}' WHERE Id = {ActionId};")
def PrepareAction(reddit, con, InputId, InputDesc, ActionId, Message):
    con.execute(f"UPDATE Actions SET ActionType = {InputId}, Description = '{InputDesc}' WHERE Id = {ActionId};")
    ActionDetailRows = GetActionDetail(con, '', ActionId,'')
    ActionDetailRow = ActionDetailRows[0]
    modmail = CreateModMail(Message, ActionDetailRow['Link'],ActionDetailRow['TypeDesc'],ActionDetailRow['Details'],ActionDetailRow['User'],con)
    LinkType = GetLinkType(f"https://{ActionDetailRow['Link']}",con)
    if LinkType == 1:
        praw.models.Submission(reddit,url = f"https://{ActionDetailRow['Link']}").mod.remove()
    else:
        praw.models.Comment(reddit,url = f"https://{ActionDetailRow['Link']}").mod.remove()
    return {'ActionDetailRow': ActionDetailRow, 'ModMail': modmail}

def BanUser(reddit,sSubReddit,BanDays,ActionDetailRow, modmail, ActionId,con):
    sub = reddit.subreddit(sSubReddit)
    try:
        if int(BanDays) > 0:
            sub.banned.add(ActionDetailRow['User'],ban_reason=ActionDetailRow['TypeDesc'], duration=int(BanDays), ban_message=modmail)
            return f"Usuario banneado por {BanDays} dias."
        sub.banned.add(ActionDetailRow['User'],ban_reason=ActionDetailRow['TypeDesc'], ban_message=modmail)
        return f"Usuario banneado permanentemente."
    except: 
        #unwarn ActionId rollback
        Unwarn(con,f"{ActionId}")
        return f"Ocurrio un error al intentar bannear al usuario: {sys.exc_info()[1]}"
def GetActionDetail(con, Link, ActionId, User):
    sQuery = f"SELECT ifnull(m.RedditName,'Deleted Mod Id ' + a.Mod), ifnull(t.Description,'Deleted Reason Id ' + a.ActionType), a.Description, a.Date, a.Link, a.User, a.Id, t.Weight,  '<@' ||  m.DiscordID ||  '>' FROM Actions a left join Moderators m on m.Id = a.Mod left join ActionType t on t.Id = a.ActionType "
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

def InitAction(Link, con, reddit, SenderAction):
    linkType = GetLinkType(Link,con)
    if linkType > 0:
        rows = GetActionDetail(con, Link, 0,'')
        if len(rows) > 0:
            if rows[0]['TypeDesc'] is None:
                return f"[NoDel]Ese link esta a la espera de que el Moderador {rows[0]['DiscordId']} elija el motivo de la sancion."
            return f"Ese link ya fue sancionado por Mod: {rows[0]['ModName']} \nFecha: {rows[0]['Date']} \nMotivo: {rows[0]['TypeDesc']}\nDetalles: {rows[0]['Details']}"
        else:
            if linkType == 1:
                submission = praw.models.Submission(reddit,url = Link)
                AuthorName = submission.author.name
            else:
                comment = praw.models.Comment(reddit,url = Link)
                AuthorName = comment.author.name  # This returns a ``Redditor`` object.
            row = (AuthorName, SanatizeRedditLink(Link,con), SenderAction['modID'],datetime.now() )
            con.execute("""INSERT INTO Actions (User, Link, Mod, Date) VALUES (?,?,?,?);""", row)
            return f"Selecciona un motivo #<Id>, <Descripcion (Opcional)> \n{GetActionTypes(con,AuthorName)}"
    return None
client.run(TOKEN)