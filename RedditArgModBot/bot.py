# bot.py
import os
import sqlite3 as sl
import discord
import praw
import sys
import asyncio
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
        if message.content.lower().strip(' ')=="gary":
            Response = "gary - Muestra esta ayuda\nwarns <user> - Muestra los warns de un usuario\nunwarn <id> - Elimina un warn especifico\nunban <user> - desbannea a un usuario\nmods - funciones de moderador\nsettings - configura las preferencias\npolicies - configura las politicas de moderacion\nreasons - configura los motivos de sancion\n<link> - inicia el proceso de warn"
        elif message.content.lower().startswith('warns '):
            Response = GetWarns(con,message.content[6:].strip(' '))
        elif message.content.lower().startswith('unwarn '):
            Response = Unwarn(con,message.content[7:].strip(' '))
        elif message.content.lower().startswith('unban '):
            Response = Unban(message.content[6:].strip(' '), reddit,con)
        elif message.content.lower().startswith('mods'):
            Response = HandleMods(con,message.content[5:].strip(' '))
        elif message.content.lower().startswith('settings'):
            Response = HandleSettings(con,message.content[9:].strip(' '))
        elif message.content.lower().startswith('policies'):
            Response = HandlePolicies(con,message.content[9:].strip(' '))
        elif message.content.lower().startswith('reasons'):
            Response = HandleReasons(con,message.content[8:].strip(' '))
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
            for indRes in Sectionize(Response):
                Msgs.append(await message.channel.send(indRes))
            seconds = int(GetSetting(con,"DelMsgAfterSeconds"))
            if seconds > 0:
                await asyncio.sleep(seconds)
                for Msg in Msgs:
                    await Msg.delete()

    if message.content == 'raise-exception':
        raise discord.DiscordException
def Sectionize(sIn):
    Max = int(os.getenv('DiscordMaxChars'))
    sIn = sIn.strip("\n")
    chunks = sIn.split("--------------------")
    retChunks = []
    sRet = ""
    for chunk in chunks:
        chunk = chunk.strip("\n")
        if len(chunk) > 0:
            if len(sRet + chunk + "\n--------------------\n") > Max:
                if len(sRet) == 0: #this chunk is larger than the limit by itself, cut it in pieces
                    while len(chunk) > Max:
                        retChunks.append(chunk[:Max])
                        chunk = chunk[Max:]
                    retChunks.append(chunk)
                else: #The concat of chunks went over the limit on this set, don't use this last chunk for now, add it to the next set
                    retChunks.append(sRet)
                    sRet = chunk + "\n--------------------\n"
            else:
                sRet = sRet + chunk + "\n--------------------\n"
    retChunks.append(sRet.rstrip("\n--------------------\n"))
    return retChunks
def SanatizeRedditLink(sIn,con):
    sIn = sIn.lstrip('http')
    sIn = sIn.lstrip('s')
    sIn = sIn.lstrip('://')
    sIn = sIn.lstrip('www.')
    sIn = sIn.lstrip('old.') 
    if sIn.startswith('reddit.com') and GetSetting(con,"subreddit").lower() in sIn.lower():
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
def HandleReasons(con,sCommand):
    if sCommand.lower().startswith('list'):
        return GetReasons(con)
    if sCommand.lower().startswith('edit '):
        return EditReason(con,sCommand[4:].strip(' '))
    if sCommand.lower().startswith('remove '):
        return RemoveReason(con, sCommand[7:].strip(' '))
    else:
        return "reasons list - Muestra un listado de los motivos\nreasons remove <id> - Elimina un motivo\nreasons edit <id(entero, si esta vacio es un nuevo registro)>,<Descripcion(texto, obligatorio)>,<BanDays(entero, si es -1 es permanente)>,<Message(Texto)> - Agrega o edita un motivo"
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

def GetSetting(con,setting):
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
    sRetu = ''
    dateFrom = datetime.now() - timedelta(days=int(GetSetting(con,"warnexpires")))
    iWeight = 0
    for row in rows:
        if datetime.strptime(row['Date'], '%Y-%m-%d %H:%M:%S.%f') >= dateFrom:
            sActive = "Si"
            iWeight = iWeight + row['Weight']
        else:
            sActive = "No"
        sRetu = sRetu + f"Warn Id: {row['Id']} \nMod: {row['ModName']} \nFecha: {row['Date']}\nActivo: {sActive}\nLink: {row['Link']}\nMotivo: {row['TypeDesc']}\nPuntos: {row['Weight']}\nDetalles: {row['Details']}\n--------------------\n"
    if len(sRetu) == 0:
        sRetu = f"No se encontaron warns para el usuario {sUser}"
    else:
        sRetu = sRetu + f"Total: {iWeight} Puntos"
    return sRetu
def GetWarnsUserReport(con,sUser):
    rows = GetActionDetail(con, '', 0,sUser)
    sRetu = ""
    dateFrom = datetime.now() - timedelta(days=int(GetSetting(con,"warnexpires")))
    iWeight = 0
    for row in rows:
        if datetime.strptime(row['Date'], '%Y-%m-%d %H:%M:%S.%f') >= dateFrom:
            sRetu = sRetu + f"{row['Date'].split(' ')[0]}\t[{row['TypeDesc']}](https://{row['Link']})\tPuntos: {row['Weight']}\n\n"
            iWeight += row['Weight']
    sRetu = sRetu + f"**Total**: {iWeight}"
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

def GetActionTypes(con, UserName):

    sRetu = ""
    Weight = GetUsersCurrentWeight(con,UserName)
    cur = con.cursor()
    cur.execute(f"SELECT t.Id, t.Description, p.Action, p.BanDays FROM ActionType t join Policies p on p.[From] <= t.Weight + {Weight} and p.[To] >= t.Weight + {Weight} Where t.Active = 1 order by t.Id")
    rows = cur.fetchall()
    for row in rows:
        sRetu = f"{sRetu}#{row[0]} - {row[1]} - **Action:** "
        if row[2] == 1:
            sRetu = sRetu + "Advertencia"
        else:
            sRetu = sRetu + "Ban "
            if row[3] < 1:
                sRetu = sRetu + "Permanente"
            else:
                sRetu = sRetu + f"{row[3]} Dias"
        sRetu = sRetu + "\n"
    return sRetu

def DeletePending(con, Id):
    con.execute(f"DELETE FROM Actions WHERE Id = {Id}")

def ValidateActionType(con, Id):
    cur = con.cursor()
    cur.execute(f"SELECT Weight FROM ActionType WHERE Id = {Id} and Active = 1")
    rows = cur.fetchall()
    if len(rows) > 0:
        return int(rows[0][0])
    return 0
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
        Weight = GetUsersCurrentWeight(con, rows[0][0]) + AddedWeight
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
        sMessage = sMessage.replace("[Summary]", GetWarnsUserReport(con,sUser))
    sMessage = sMessage.replace("\\n", "\n")
    return sMessage[:1000]

def ResolveAction(con, sIn, ActionId, reddit):
    if not sIn.startswith('#'):
        return None
    Input = SanatizeInput(sIn)
    Weight = ValidateActionType(con, Input['Id'])
    if Weight > 0:
        ApplyingPol = GetApplyingPolicy(con,ActionId, Weight)
        if ApplyingPol['Action'] > 0:
            preparedAction = PrepareAction(reddit,con,Input['Id'],Input['Description'],ActionId,ApplyingPol['Message'])
            ActionDetailRow = preparedAction["ActionDetailRow"]
            modmail = preparedAction["ModMail"]
            sSubReddit = GetSetting(con,"subreddit")
            if ApplyingPol['Action'] == 1: #Warn
                reddit.redditor(ActionDetailRow['User']).message(f"Equipo de Moderacion de /r/{sSubReddit}",modmail, from_subreddit=sSubReddit)
            if ApplyingPol['Action'] == 2: #Ban
                return BanUser(reddit,sSubReddit,ApplyingPol['BanDays'],ActionDetailRow, modmail, ActionId,con)
            return "Usuario advertido."
            #Aca va la parte en donde vemos que hacemos con las politicas
        return "Error al buscar politica"
    else:
        return "Formato incorrecto, por favor ingresa el motivo usando los IDs correspondientes"
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
    sQuery = f"SELECT ifnull(m.RedditName,'Deleted Mod Id ' + a.Mod), ifnull(t.Description,'Deleted Reason Id ' + a.ActionType), a.Description, a.Date, a.Link, a.User, a.Id, t.Weight FROM Actions a left join Moderators m on m.Id = a.Mod left join ActionType t on t.Id = a.ActionType "
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
        lst.append({'ModName':row[0], 'TypeDesc': row[1], 'Details':row[2], 'Date':row[3], 'Link':row[4], 'User':row[5], 'Id': row[6], 'Weight': row[7], })
    return lst

def InitAction(Link, con, reddit, SenderAction):
    linkType = GetLinkType(Link,con)
    if linkType > 0:
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
            row = (AuthorName, SanatizeRedditLink(Link,con), SenderAction['modID'],datetime.now() )
            con.execute("""INSERT INTO Actions (User, Link, Mod, Date) VALUES (?,?,?,?);""", row)
            return f"Selecciona un motivo #<Id>, <Descripcion (Opcional)> \n{GetActionTypes(con,AuthorName)}"
    return None
client.run(TOKEN)