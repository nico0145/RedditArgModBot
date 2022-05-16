import os
import re
import sys
import uuid
import dotenv
import discord
from py.DBHandle import *
from py.DiscordHandle import *
from py.StaticHelpers import *
from dotenv import load_dotenv
from dateutil.relativedelta import *
from datetime import timedelta, date
from discord.ext import tasks, commands
load_dotenv()
TOKEN = os.getenv('DiscordChatmodToken')
DB = DBHandle(os.getenv('DB'))
CommandSymbol = DB.GetSetting('ChatbotCommandSymbol')
DiscordBotChannel = DB.GetSetting('DiscordBotChannel')
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=CommandSymbol, intents=intents)
DiscordMaxChars = int(os.getenv('DiscordMaxChars'))
class UserHighlight:
    def __init__(self,Uid, Highlight,ActionId = None):
        self.Uid = Uid
        self.Highlight = Highlight
        self.ActionId = ActionId
def UpdateHighlights():
    global UserHighlights
    UserHighlights = []
    oHls = DB.ExecuteDB("Select D.DiscordId, H.Highlight, H.ActionTypeId from Highlights H join DiscordUsers D on D.Id = H.DiscordId " \
                        "join UserRoles UR on UR.DiscordId = D.Id join Roles R on R.id = UR.RoleId where R.Name = 'Discord Mod'")
    for oHl in oHls:
        UserHighlights.append(UserHighlight(oHl[0], oHl[1], oHl[2]))
UpdateHighlights()
@bot.event
async def on_ready():
    InitializeLog(os.getenv('DiscordBotLog'))
    envFile = os.path.join(os.path.dirname(os.path.abspath(__file__)) + os.path.sep, '.env')
    dotenv.set_key(envFile,"DiscordModPID",str(os.getpid()))
    Log(f"Discord mod bot connected to Discord using discord user {bot.user.name}",bcolors.OKGREEN,logging.INFO)
    rres = await async_get_reddit_object()
    if rres['status'] == 'success':
        global reddit
        reddit = rres['data']
        rUser = await reddit.user.me()
        Log(f"Discord mod bot connected to Reddit using user {rUser.name}",bcolors.OKGREEN,logging.INFO)
        await PerformCycleActions()
    else:
        Log(f"Discord mod bot couldn't connect to Reddit, status returned: {rres['status']}",bcolors.WARNING,logging.ERROR)
@bot.event
async def on_member_join(member):
    await StartVerificationProcess(member)
@bot.event
async def on_member_remove(member):
    DiscordServer = bot.get_guild(int(os.getenv('DiscordServer')))
    category = discord.utils.get(DiscordServer.categories, name = "DMs")
    if category is not None:
        channel = discord.utils.get(category.channels, name=member.name.lower())
        if channel is not None:
            await channel.delete()
def GetMessageCategoryName(message):
    if hasattr(message.channel,'category'):
        return message.channel.category.name
    return None

@bot.event
async def on_message(message):
    #await UpdateRedditUsers()
    if message.author == bot.user:
        return
    SenderInfo = CheckSender(message.author) #extending the Bot class to add some context
    await bot.process_commands(message)
    if not message.content.startswith('?') and (message.channel.type == discord.enums.ChannelType.private or message.channel.category.name == "DMs") and len(message.content) > 0:
        await HandleDM(message)
    elif 'Discord Mod' in SenderInfo.Roles and (GetMessageCategoryName(message) == "Mod mail" or GetMessageCategoryName(message) == "Archived"):
        await HandleDMResponse(message)
    else:
        if 'Discord Mod' in SenderInfo.Roles and 'Bot User' in SenderInfo.Roles  and str(message.channel.id) == DiscordBotChannel: #we only pay attention to verified mods in the right channel
            msgRetu = None
            if message.content.strip(' ')=="undo":
                if not SenderInfo.PendingAction is None:
                    DeletePending(DB, SenderInfo.PendingAction)
                    msgRetu = [Message(False,False,MessageType.Text,f"WarnID {SenderInfo.PendingAction} pendiente eliminado.")]
                else:
                    msgRetu = [Message(False,False,MessageType.Text,"No hay warnings pendientes.")]
            else:
                ActionableMessage = message.content.split('!')
                messageSanctioned = await VerifyDiscordLink(ActionableMessage[0], message.guild)
                if messageSanctioned is not None: #this is a link, valid or not
                    if type(messageSanctioned) == discord.message.Message:
                        if SenderInfo.PendingAction is not None:
                            DeletePending(DB, SenderInfo.PendingAction)
                        if len(ActionableMessage)==2:
                            asyncio.Task(FullSanctionMessage(messageSanctioned,SenderInfo, ActionableMessage[1],message.guild, message.channel, message.author))
                        else:
                            msgRetu = await InitAction(messageSanctioned, SenderInfo)
                    else:
                        msgRetu =[Message(False,False,MessageType.Text,messageSanctioned)]
                elif SenderInfo.PendingAction is not None:
                    msgRetu = await ResolveAction(message.content, message.guild, SenderInfo)
            if msgRetu is not None:
                await SendResponse(msgRetu, DB, message)

            #msgRetu = None
            #if message.content.strip(' ')=="undo":
            #    if not SenderInfo.PendingAction is None:
            #        DeletePending(DB, SenderInfo.PendingAction)
            #        Response = [Message(False,False,MessageType.Text,f"WarnID {SenderInfo.PendingAction} pendiente eliminado.")]
            #    else:
            #        Response = [Message(False,False,MessageType.Text,"No hay warnings pendientes.")]
            #verifResp = await VerifyDiscordLink(message)
            #if verifResp is not None: #this is a link, valid or not
            #    if type(verifResp) == discord.message.Message:
            #        if SenderInfo.PendingAction is not None:
            #            DeletePending(DB, SenderInfo.PendingAction)
            #        msgRetu = await InitAction(verifResp, SenderInfo)
            #    else:
            #        msgRetu =[Message(False,False,MessageType.Text,verifResp)]
            #elif SenderInfo.PendingAction is not None:
            #    msgRetu = await ResolveAction(message, SenderInfo)
            #if msgRetu is not None:
            #    await SendResponse(msgRetu, DB, message)
        if 'Bot User' not in SenderInfo.Roles: #bot users are excempt of highlights/automod rules
            oHLs = SearchHL(message.content)
            if len(oHLs) > 0:
                oAutoMods = list(filter(lambda x: x.ActionId is not None, oHLs))
                oHLs = list(filter(lambda x: x.ActionId is None, oHLs))
                if len(oHLs) > 0:
                    sRetu = f"En **{message.channel.last_message.guild.name}** <#{message.channel.id}> el usuario <@{message.author.id}> activo tu filtro de palabras: **[Filtro]**\n" \
                            f"{await GetSnapshot(message, False)}\n [Ir al mensaje]({message.jump_url})"
                    for oHL in oHLs:
                        await SendResponse([Message(True,True,MessageType.Text,sRetu.replace("[Filtro]",oHL.Highlight), oHL.Uid)], DB, message)
                #if one message breaks several automod rules at the same time it'll pick the one with the highest weight

                for oAutoMod in oAutoMods:
                    authorMod = await bot.fetch_user(oAutoMod.Uid)
                    channelRet = bot.get_channel(int(DiscordBotChannel))
                    asyncio.Task(HandleMessage(int(os.getenv('DiscordMaxChars')),DB, channelRet ,Message(False,True,MessageType.Text,f"En <#{message.channel.id}> el usuario <@{message.author.id}> activo la regla de automod: **{oAutoMod.Highlight}**\n")))
                    asyncio.Task(FullSanctionMessage(message,CheckSender(authorMod), oAutoMod.ActionId ,message.guild, channelRet, authorMod,True))
async def FullSanctionMessage(messageSanctioned,SenderInfo, ActionTypeId,messageGuild, channelResponse, authorMod, responsePersistent = None):
    Response = await InitAction(messageSanctioned, SenderInfo)
    SenderInfo = CheckSender(authorMod)
    if SenderInfo.PendingAction is not None:
        asyncio.Task(HandleMessage(int(os.getenv('DiscordMaxChars')),DB, channelResponse ,Message(False,False,MessageType.Text,f"Procesando Warn ID {SenderInfo.PendingAction}...\nAplicando medida !{ActionTypeId}")))
        Response = await ResolveAction(f"!{ActionTypeId}", messageGuild, SenderInfo)#message.content tiene que ser el motivo, ej: !12, saradeisa
        asyncio.Task(SendResponses(Response,channelResponse,responsePersistent))
async def SendResponses(Response,channelResponse,responsePersistent):
    for IndResponse in Response:
        if responsePersistent is not None:
            IndResponse.NoDel=responsePersistent
        await HandleMessage(int(os.getenv('DiscordMaxChars')),DB, channelResponse ,IndResponse)
async def HandleDMResponse(message):
    if not message.clean_content.startswith('='):
        try:
            if '┃' in message.channel.name:
                action = GetCommonActionDetail(DB, "ActionId",message.channel.name.split('┃')[1])
                if action is not None:
                    sub = await reddit.subreddit(DB.GetSetting("subreddit")[0])#Since the bot is mod in all subs it doesn't matter which one we point to, any sub will do to read modmail
                    conversation = await sub.modmail(action['ModmailID'])
                    reply = await conversation.reply(body = message.content, author_hidden = True)
                    await conversation.archive()
                    DB.WriteDB(f"update Actions set LastModmailUpdated = '{reply.date}' where modmailID = '{action['ModmailID']}'")
            else:
                RespUserId = DB.GetDBValue(f"Select DiscordId from DiscordUsers where lower(Name) = '{message.channel.name}'")
                if RespUserId is not None:
                    await SendResponse([Message(False,True,MessageType.Text,message.content,RespUserId)], DB, message)
            await message.add_reaction('✅')
        except:
            await message.add_reaction('❌')
    elif message.clean_content.lower().startswith('=archivar'):
        ArchiveCat = discord.utils.get(message.channel.guild.categories, name = "Archived")
        await message.channel.edit(category = ArchiveCat)
async def HandleDM(message):
    try:
        UserName = DB.GetDBValue(f"Select Name from DiscordUsers where DiscordId = {message.author.id}")
        channel = await GetDMChannel(UserName)
        if channel is not None:
            LastAction = GetLastActionDetail(message.author.id)
            if LastAction is not None:
                MsgHistory = await channel.history(limit=None, after=datetime.strptime(LastAction['Date'], '%Y-%m-%d %H:%M:%S.%f') - timedelta(hours=1)).flatten() #remove 1 hour because of UTC :S
                if not any(x.author.id == bot.user.id for x in MsgHistory):
                    embMsg = discord.Embed()
                    embMsg.description  = f"{UserName} Respondio al DM generado por:\n{LastAction['TypeDesc']}\n\n**Log**:\n{LastAction['Snapshot']}\n\nResponde en este canal de forma anonima.\nLos mensajes que empiecen con '=' no seran enviados al usuario."
                    await channel.send(LastAction['DiscordId'],embed=embMsg)
            await channel.send(f"[{message.created_at.strftime('%Y-%m-%d %H:%M:%S')}] **{UserName}**: {message.content}")
            await message.add_reaction('✅')
    except:
        await message.add_reaction('❌')
async def GetDMChannel(UserName):
    DiscordServer = bot.get_guild(int(os.getenv('DiscordServer')))
    category = discord.utils.get(DiscordServer.categories, name = "Mod mail")
    ArchiveCat = discord.utils.get(DiscordServer.categories, name = "Archived")
    if ArchiveCat is not None and UserName is not None:
        channel = discord.utils.get(ArchiveCat.channels, name=UserName.lower())
        if channel is not None:
            await channel.edit(category = category)
            return channel
    if category is not None and UserName is not None:
        channel = discord.utils.get(category.channels, name=UserName.lower())
        if channel is None:
            channel = await DiscordServer.create_text_channel(category=category, name = UserName.lower(),topic="Los mensajes que empiecen con '=' no seran enviados al usuario")
        return channel
    return None
async def ArchiveModmail():
    DiscordServer = bot.get_guild(int(os.getenv('DiscordServer')))
    ModmailCat = discord.utils.get(DiscordServer.categories, name = "Mod mail")
    ArchiveCat = discord.utils.get(DiscordServer.categories, name = "Archived")
    DMCat = discord.utils.get(DiscordServer.categories, name = "DMs")
    diasArchivarModmail = int(DB.GetSetting("diasArchivarModmail"))
    diasPurgarArchivo = int(DB.GetSetting("diasPurgarArchivo"))
    diasPurgarDMChannel = int(DB.GetSetting("diasPurgarDMChannel"))
    for channel in ModmailCat.channels:
        MsgHistory = await channel.history(limit=1).flatten()
        if len(MsgHistory) > 0:
            if MsgHistory[0].created_at < datetime.now() -timedelta(days=diasArchivarModmail):
                await channel.edit(category = ArchiveCat)
    for channel in ArchiveCat.channels:
        MsgHistory = await channel.history(limit=1).flatten()
        if len(MsgHistory) > 0:
            if MsgHistory[0].created_at < datetime.now() -timedelta(days=diasPurgarArchivo):
                await channel.edit(sync_permissions=True)
                await channel.delete()
    for channel in DMCat.channels:
        MsgHistory = await channel.history(limit=1).flatten()
        if len(MsgHistory) > 0:
            if MsgHistory[0].created_at < datetime.now() -timedelta(days=diasPurgarDMChannel) or (MsgHistory[0].author == bot.user and len(MsgHistory[0].embeds) > 0 and MsgHistory[0].embeds[0].description.startswith("Bienvenido al server de Discord") and MsgHistory[0].created_at < datetime.now() -timedelta(days=1)):
                await channel.delete()
def GetLastActionDetail(DiscordID):
    actions = GetCommonActionDetails(DB, "DiscordId",DiscordID)
    amt = len(actions)
    if amt > 0:
        return actions[amt - 1]
    return None
def GetUserByID(ID):
    return DB.GetDBValue(f"SELECT DiscordUserId FROM Actions where Id = {ID}")
async def ResolveAction(messageContent, messageGuild, senderinfo):
    if not messageContent.startswith('!'):
        return [Message(False,False,MessageType.Text,f"Selecciona un motivo !<Id>, <Descripcion (Opcional)> \n{GetActionTypes(GetUserByID(senderinfo.PendingAction),messageContent.strip(' '))}\nUndo - Deshacer warn.")]
    Input = SanatizeInput(messageContent)
    Weight = ValidateActionType(DB, Input['Id'])
    if Weight > -1:
        ApplyingPol = GetApplyingPolicy(senderinfo.PendingAction, Weight)
        if ApplyingPol['Action'] > 0:
            try:
                #Mark action as processing
                DB.WriteDB(f"Update Actions set Processing = 1 where Id = {senderinfo.PendingAction}")
                preparedAction = await ExecuteAction(Input['Id'],Input['Description'],ApplyingPol['Message'], messageGuild, senderinfo)
                sRetu = await NotifyRedditUser(DB, reddit, preparedAction, ApplyingPol, senderinfo.PendingAction,"Discord")
                msgRet =  [Message(False,False,MessageType.Text,f"Reddit: {sRetu}")]
                sRetu = await NotifyDiscordUser(DB,bot,preparedAction,ApplyingPol,senderinfo.PendingAction)
                msgRet.append(Message(False,False,MessageType.Text,f"Discord: {sRetu}"))
                return msgRet
            except Exception as err:
                #unmark processing
                DB.WriteDB(f"Update Actions set Processing = null where Id = {senderinfo.PendingAction}")
                if sys.exc_info()[0] is ExecuteActionException:
                    return [Message(False,False,MessageType.Text,f"Ocurrio un error al intentar borrar el post: {err.custom_code}")]
                return [Message(False,False,MessageType.Text,f"Ocurrio un error al intentar borrar el post: {sys.exc_info()[1]}")]
        return [Message(False,False,MessageType.Text,"Error al buscar politica")]
    else:
        return [Message(False,False,MessageType.Text,"Formato incorrecto, por favor ingresa el motivo usando los IDs correspondientes")]
async def GetSnapshot(msg, IsModmail):
    MsgHistory = await msg.channel.history(limit=5, before=msg).flatten()
    snapshot = f"{msg.channel.category.name}-#{msg.channel.name}\n"
    for i in range(len(MsgHistory) - 1, -1, -1):
        snapshot = f"{snapshot}{FormatSnapshot(MsgHistory[i], IsModmail)}"
    return f"{snapshot}{FormatSnapshot(msg, IsModmail)}"
def FormatSnapshot(message, IsModmail):
    if IsModmail:
        if message.author == bot.user:
            if message.channel.name in message.clean_content.lower():
                return f"{message.clean_content}\n\n"
            return ""
        if message.clean_content.startswith('='):
            return ""
        return f"**[{message.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {bot.user.name}**: {message.clean_content}\n\n"
    return f"**[{message.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {message.author.display_name}**: {message.clean_content}\n\n"
async def ExecuteAction(InputId, InputDesc, Message, messageGuild, senderinfo):
    ActionDetailRow = GetCommonActionDetail(DB, "ActionId",senderinfo.PendingAction)
    msg = await VerifyDiscordLinkStr(ActionDetailRow['Link'], messageGuild)
    if msg is not None:
        bIsModmail = msg.author == bot.user and msg.channel.category.name == 'Mod mail'
        snapshot = await GetSnapshot(msg, bIsModmail)
        if not bIsModmail:
            await msg.delete()
        params = (InputId,InputDesc,snapshot,senderinfo.PendingAction)
        DB.WriteDB( f"UPDATE Actions SET Processing = null, ActionType = ?, Description = ?, Snapshot = ? WHERE Id = ?;", params)
        ActionDetailRow = GetCommonActionDetail(DB, "ActionId",senderinfo.PendingAction)
        modmail = await CreateModMail(Message, ActionDetailRow['Link'],ActionDetailRow['TypeDesc'],ActionDetailRow['Details'],ActionDetailRow['User'],ActionDetailRow['RuleLink'],ActionDetailRow['Snapshot'], reddit, DB)
        return {'ActionDetailRow': ActionDetailRow, 'ModMail': modmail}
    else:
        raise ExecuteActionException(f"Mensaje {ActionDetailRow['Link']} no encontrado")

def GetApplyingPolicy(ActionId, AddedWeight):
    dUid = DB.GetDBValue(f"Select DiscordUserId FROM Actions WHERE Id = {ActionId}")
    if dUid is not None:
        if AddedWeight > 0:
            Weight = GetUsersCurrentWeight(dUid) + AddedWeight
        else:
            Weight = AddedWeight
        rows = DB.ExecuteDB(f"Select Action, BanDays, Message FROM Policies WHERE [From] <= {Weight} and [To] >= {Weight}")
        if len(rows) > 0:
            return {'Action':rows[0][0], 'BanDays': rows[0][1], 'Message':rows[0][2]}
    return  {'Action':0, 'BanDays': '0', 'Message':'0'}
def GetCurrentPolicy(dUid):
    Weight = GetUsersCurrentWeight(dUid)
    rows = DB.ExecuteDB(f"Select Action, BanDays, Message FROM Policies WHERE [From] <= {Weight} and [To] >= {Weight}")
    if len(rows) > 0:
        return {'Action':rows[0][0], 'BanDays': rows[0][1], 'Message':rows[0][2]}
    return  {'Action':0, 'BanDays': '0', 'Message':'0'}
def GetActionDetail(message, ActionId, ByLink, ByUser):
    oRet = GetActionDetails(message, ActionId, ByLink, ByUser)
    if len(oRet)> 0:
        return oRet[0]
    return None
def SanatizeDiscordLink(Link):
    return Link.replace("https://discord.com/channels/",'')
async def InitAction(message, senderinfo):
    ActionDetail = GetCommonActionDetail(DB, "Link",SanatizeDiscordLink(message.jump_url))
    if ActionDetail is not None:
        if ActionDetail['TypeDesc'] is None:
            return [Message(False,True,MessageType.Text,f"Ese link esta a la espera de que el Moderador {ActionDetail['DiscordId']} elija el motivo de la sancion.")]
        return [Message(False,False,MessageType.Text,f"Ese link ya fue sancionado por Mod: {ActionDetail['ModName']} \nFecha: {ActionDetail['Date']} \nMotivo: {ActionDetail['TypeDesc']}\nDetalles: {ActionDetail['Details']}")]
    else:
        if message.author == bot.user and message.channel.category.name == 'Mod mail':
            DUser = DB.ExecuteDB(f"Select Id, DiscordId from DiscordUsers where lower(Name) = '{message.channel.name}'")[0]
            DUid = DUser[0]
            dAuthor = await bot.fetch_user(int(DUser[1]))
        else:
            DUid = GetDiscordUID(message)
            dAuthor = message.author
        DB.WriteDB("INSERT INTO Actions (Link, Mod, Date, DiscordUserId) VALUES (?,?,?,?);",(SanatizeDiscordLink(message.jump_url),senderinfo.Id,datetime.now(),DUid))
        msgRetu = GetWarns(dAuthor,True)
        msgRetu.append(Message(False,False,MessageType.Text,f"Selecciona un motivo #<Id>, <Descripcion (Opcional)> \n{GetActionTypes(DUid)}\nUndo - Deshacer warn."))
        return msgRetu
def GetDiscordUID(message):
    return DB.GetDBValue(f"Select Id from DiscordUsers where DiscordId = {message.author.id}")
def GetActionTypes(UId, filter = "", FormatTable = False):
    sRetu = ""
    Weight = GetUsersCurrentWeight(UId)
    sQuery = f"SELECT '!' || t.Id as Id, t.Description as Descripcion, case t.Weight when 0 then 'Advertencia' else case p.Action when 1 then 'Advertencia' when 2 then case p.BanDays when -1 then 'Ban Permanente' else 'Ban ' || p.BanDays || ' Dias' End End End as Accion, t.Weight as Puntos FROM ActionType t join Policies p on p.[From] <= t.Weight + {Weight} and p.[To] >= t.Weight + {Weight} Where t.Active = 1 and t.Description like '%{filter}%' order by trim(t.Description), t.Weight desc"
    if FormatTable:
        return DB.GetTable(sQuery)
    rows = DB.ExecuteDB(sQuery)
    for row in rows:
        sRetu = f"{sRetu}{row[0]} - {row[1]} - **Puntos:** {row[3]} - **Accion: {row[2]} **\n"
    return sRetu
def GetUsersCurrentWeight(UId):
    dateFrom = datetime.now() - timedelta(days=int(DB.GetSetting("warnexpires")))
    return  DB.GetDBValue("select sum(Weight) as Weight from( " \
            "Select ifnull(Sum(t.Weight),0) as Weight " \
            "FROM Actions a  " \
            "Join ActionType t on t.Id = a.ActionType  " \
            f"where A.DiscordUserId = {UId} " \
            f"and a.Date >= '{dateFrom}' " \
            "union " \
            "Select ifnull(Sum(t.Weight),0) as Weight " \
            "FROM Actions a  " \
            "Join ActionType t on t.Id = a.ActionType  " \
            "join DiscordRedditUser DRU on DRU.RedditId = A.RedditUserId " \
            f"where DRU.DiscordId = {UId} " \
            f"and a.Date >= '{dateFrom}')  ")
def GetWarns(author, summary = False):
    rows =  GetCommonActionDetails(DB, "DiscordId",author.id)
    sRetu = f"**Warns del usuario {author.name}**\n"
    dateFrom = datetime.now() - timedelta(days=int(DB.GetSetting("warnexpires")))
    iWeight = 0
    for row in rows:
        if datetime.strptime(row['Date'], '%Y-%m-%d %H:%M:%S.%f') >= dateFrom:
            sActive = "Si"
            if not row['Weight'] is None:
                iWeight = iWeight + row['Weight']
        else:
            sActive = "No"
        if row['Link'].startswith('reddit.com'):
            sLink = f"[{row['TypeDesc']}](https://{row['Link']})"
        else:
            sLink = f"(Discord) {row['TypeDesc']}"
        if summary:
            sRetu += f"{sLink} - Puntos: {row['Weight']}\n"
        else:
            sRetu += f"Warn Id: {row['Id']} \nMod: {row['ModName']} \nFecha: {row['Date']}\nActivo: {sActive}\n{sLink}\nPuntos: {row['Weight']}\nDetalles: {row['Details']}\n"
            if row['Snapshot'] is not None and len(row['Snapshot']) > 0:
                sRetu = f"{sRetu}Snapshot:\n{row['Snapshot']}\n"
            sRetu += "--------------------\n"
    if len(sRetu) == 0:
        sRetu = f"No se encontaron warns para el usuario {sUser}"
    else:
        sRetu += f"Total: {iWeight} Puntos"
    return [Message(True,False,MessageType.Text,sRetu)]
async def VerifyDiscordLink(message):
    return await VerifyDiscordLink(message.content, message.guild)
async def VerifyDiscordLink(messageContent, messageGuild):
    if messageContent.startswith("https://discord.com/channels/"):
        return await VerifyDiscordLinkStr(SanatizeDiscordLink(messageContent), messageGuild)
    return None
async def VerifyDiscordLinkStr(sAux, Server):
    msgInfo = sAux.split('/')
    if msgInfo[0] == str(Server.id):
        chan = Server.get_channel(int(msgInfo[1]))
        if chan is not None:
            msg = await chan.fetch_message(int(msgInfo[2]))
            if msg is not None:
                return msg
    return "El link no corresponde a este server o su formato es incorrecto"
    #278285146518716417/279701101152960512/920088707485286401
@bot.command()
async def ayuda(message):
    SenderInfo = CheckSender(message.author)
    sRetu = f"{CommandSymbol}ayuda - Muestra esta ayuda\n{CommandSymbol}verificar - Inicia el proceso de verificacion con tu cuenta de Reddit\n"
    if 'Discord Mod' in SenderInfo.Roles:
        sRetu = f"{sRetu}{CommandSymbol}hl - Administra tus palabras destacadas"
    await SendResponse([Message(False,False,MessageType.Text,sRetu)], DB, message)
@bot.command()
async def anunciar(message):
    SenderInfo = CheckSender(message.author)
    if 'Discord Mod' in SenderInfo.Roles:
        sChannel = message.message.content[len("?anunciar "):].split(',')[0].strip(' ')
        if sChannel.isnumeric():
            oChannel = bot.get_channel(int(sChannel))
            if oChannel is not None:
                sMessage = message.message.content[len("?anunciar "):].strip(' ')[len(sChannel):].lstrip(',').strip(' ')
                asyncio.Task(HandleMessage(DiscordMaxChars,DB, oChannel,Message(False,True,MessageType.Text,sMessage)))
        else:
            await SendResponse([Message(False,False,MessageType.Text,f"Formato incorrecto, el comando es {CommandSymbol}anunciar <ChannelID>,<Mensaje>")] , DB, message)
@bot.command()
async def automod(message):
    SenderInfo = CheckSender(message.author)
    if 'Bot User' in SenderInfo.Roles and 'Discord Mod' in SenderInfo.Roles: 
        StandardMessage = message.message.content.lower()[8:].strip(' ')
        if StandardMessage.startswith('add '):
            await SendResponse(AddAutomodFilterRule(StandardMessage[4:].strip(' '), SenderInfo) , DB, message)
            UpdateHighlights()
        elif StandardMessage.startswith('del '):
            await SendResponse(DelAutomodFilterRule(StandardMessage[4:].strip(' '), SenderInfo) , DB, message)
            UpdateHighlights()
        elif StandardMessage == 'list':
            await SendResponse(ShowAutomodFilterRules(SenderInfo) , DB, message)
            UpdateHighlights()
        else:
            await SendResponse([Message(False,False,MessageType.Text,f"{CommandSymbol}automod add <string>, <ID de la sancion (reasons list)> - Agrega una regla de automod\n{CommandSymbol}automod del <string> elimina una regla de automod\n{CommandSymbol}automod list - Muestra todas las reglas del automod")] , DB, message)
    else:
        await SendResponse([Message(False,False,MessageType.Text,f"Se requiere del rol Discord Mod para realizar esta accion")] , DB, message)
def ShowAutomodFilterRules(SenderInfo):
    return [Message(False,False,MessageType.Text,DB.GetTable("Select H.Highlight as 'Palabras destacadas', A.Description as 'Regla', A.Weight as 'Puntos' " \
                                                            "from Highlights H " \
                                                            "join ActionType A on A.Id = H.ActionTypeId " \
                                                            f"Where H.ActionTypeId is not NULL"))]
def AddAutomodFilterRule(sIn,SenderInfo):
    oIn = sIn.split(',')
    if len(oIn) >= 2:
        sRuleId = oIn[len(oIn)-1].strip(' ')
        if sRuleId.isnumeric():
            sFilter = sIn[:len(sRuleId)*-1].rstrip(',')
            Weight = ValidateActionType(DB, sRuleId)
            if Weight > -1:
                Id = DB.GetDBValue(f"Select Id from Highlights where Highlight = '{sFilter}' and ActionTypeId is not NULL")
                if Id is not None:
                    return [Message(False,False,MessageType.Text,f"{sFilter} ya es un filtro del Automod")]
                DB.WriteDB("Insert into Highlights(DiscordId, Highlight, ActionTypeId) Values(?,?,?)",(SenderInfo.Id, sFilter,sRuleId))
                return [Message(False,False,MessageType.Text,f"{sFilter} fue agreado a los filtros del automod")]
            else:
                return [Message(False,False,MessageType.Text,"Formato incorrecto, por favor ingresa el motivo usando los IDs correspondientes")]
        else:
            return [Message(False,False,MessageType.Text,"Formato incorrecto, por favor ingresa el motivo usando los IDs correspondientes")]
    else:
        return [Message(False,False,MessageType.Text,f"Formato incorrecto, el comando es {CommandSymbol}automod add <filtro>, <ID de la sancion (reasons list)>")]
def DelAutomodFilterRule(sIn, SenderInfo):
    Id = DB.GetDBValue(f"Select Id from Highlights where Highlight = '{sIn}' and ActionTypeId is not NULL")
    if Id is not None:
        DB.WriteDB(f"Delete from Highlights where Id = {Id}")
        return [Message(False,False,MessageType.Text,f"Se elimino {sIn} de los filtros del automod")]
    else:
        return [Message(False,False,MessageType.Text,f"{sIn} no es uno de los filtros del automod")]
@bot.command()
async def sync(message):
    SenderInfo = CheckSender(message.author)
    if 'Discord Mod' in SenderInfo.Roles:
        sCat = message.message.content[len("?sync "):].split(',')[0].strip(' ')
        if len(sCat)>0:
            oCat = discord.utils.get(message.guild.categories, name = sCat)
            if oCat is not None:
                for channel in oCat.channels:
                    await channel.edit(sync_permissions=True)
                await SendResponse([Message(False,False,MessageType.Text,f"Categoria {sCat} Sincronizada")] , DB, message)
            else:
                await SendResponse([Message(False,False,MessageType.Text,f"No se encontro la categoria {sCat}")] , DB, message)
        else:
            await SendResponse([Message(False,False,MessageType.Text,f"Formato incorrecto, el comando es {CommandSymbol}sync <categoria>")] , DB, message)
def SearchHL(sIn):
    #filter exact words
    Filtered = list(filter(lambda x: x.Highlight in sIn \
                                or (x.Highlight.startswith('"') and x.Highlight.endswith('"') \
                                    and (sIn.endswith(" "+ x.Highlight.replace('"',''))\
                                        or sIn.startswith(x.Highlight.replace('"','') + " ")\
                                        or " " + x.Highlight.replace('"','') + " " in sIn \
                                        or sIn == x.Highlight.replace('"',''))), UserHighlights))
    #filter with wildcards if nothing is found
    if len(Filtered) == 0:
        Filtered = list(filter(lambda x: re.search( f"^{x.Highlight.replace('*','(.*)')}$",sIn) is not None, UserHighlights))
    return Filtered
@bot.command()
async def hl(message):
    SenderInfo = CheckSender(message.author)
    if 'Bot User' in SenderInfo.Roles and 'Discord Mod' in SenderInfo.Roles: 
        StandardMessage = message.message.content.lower()[3:].strip(' ')
        if StandardMessage.startswith('add '):
            await SendResponse(AddHighlight(StandardMessage[4:].strip(' '), SenderInfo) , DB, message)
            UpdateHighlights()
        elif StandardMessage.startswith('del '):
            await SendResponse(DelHighlight(StandardMessage[4:].strip(' '), SenderInfo) , DB, message)
            UpdateHighlights()
        elif StandardMessage == 'list':
            await SendResponse(ShowHighlights(SenderInfo) , DB, message)
        elif StandardMessage == 'clear':
            await SendResponse(ClearHighlights(SenderInfo) , DB, message)
            UpdateHighlights()
        else:
            await SendResponse([Message(False,False,MessageType.Text,f"{CommandSymbol}hl add <string> - Agrega una palabra destacada\n{CommandSymbol}hl del <string> elimina una palabra destacada\n{CommandSymbol}hl clear - Elimina todas tus palabras destacadas\n{CommandSymbol}hl list - Muestra todas tus palabras destacadas")] , DB, message)
    else:
        await SendResponse([Message(False,False,MessageType.Text,f"Se requiere del rol Discord Mod para realizar esta accion")] , DB, message)
def AddHighlight(sIn,SenderInfo):
    Id = DB.GetDBValue(f"Select Id from Highlights where DiscordId = {SenderInfo.Id} and Highlight = '{sIn}' and ActionTypeId is NULL")
    if Id is not None:
        return [Message(False,False,MessageType.Text,f"{sIn} ya es un string destacado")]
    DB.WriteDB("Insert into Highlights(DiscordId, Highlight) Values(?,?)",(SenderInfo.Id, sIn))
    return [Message(False,False,MessageType.Text,f"{sIn} fue agreado a tus strings destacados")]
def ShowHighlights(SenderInfo):
    return [Message(False,False,MessageType.Text,DB.GetTable("Select Highlight as 'Palabras destacadas' " \
                                                            "from Highlights " \
                                                            f"Where DiscordId = {SenderInfo.Id} and ActionTypeId is NULL"))]
def DelHighlight(sIn, SenderInfo):
    Id = DB.GetDBValue(f"Select Id from Highlights where DiscordId = {SenderInfo.Id} and Highlight = '{sIn}' and ActionTypeId is NULL")
    if Id is not None:
        DB.WriteDB(f"Delete from Highlights where Id = {Id}")
        return [Message(False,False,MessageType.Text,f"Se elimino {sIn} de tus palabras destacadas")]
    else:
        return [Message(False,False,MessageType.Text,f"{sIn} no es una de tus palabras destacadas")]
def ClearHighlights(SenderInfo):
    DB.WriteDB(f"Delete from Highlights where DiscordId = {SenderInfo.Id} and ActionTypeId is NULL")
    return [Message(False,False,MessageType.Text,"Se eliminaron todas las palabras destacadas")]

def UpdateActionsTable():
    Regs = DB.ExecuteDB("select Id,User from actions where RedditUserId is null")
    for reg in Regs:
        rUID = DB.GetDBValue(f"Select Id from RedditUsers where RedditName = '{sName}'")
@bot.command()
async def verificar(message):
    SenderInfo = CheckSender(message.author)
    DiscordId = message.message.clean_content[len("?verificar"):].strip(' ')
    if 'Discord Mod' in SenderInfo.Roles and  DiscordId.isnumeric():
        DiscordServer = bot.get_guild(int(os.getenv('DiscordServer')))
        DiscordUser = DiscordServer.get_member(int(DiscordId))
    else:
        DiscordUser = message.author
    if DiscordUser is not None:
        await StartVerificationProcess(DiscordUser)
async def StartVerificationProcess(member):
    Log(f"Verifying discord user {member.id} - {member.name}",bcolors.OKBLUE,logging.INFO)
    DUID = DB.GetDBValue(f"select Id from DiscordUsers where DiscordId = {member.id}")
    Uid = str(uuid.uuid4())
    if DUID is None:
        Params = (member.name, member.id, Uid)
        Log(f"Creating new DiscordUsers register for Name: {member.name} - DiscordId: {member.id} - LinkKey: {Uid}",bcolors.OKBLUE,logging.INFO)
        DB.WriteDB("Insert into DiscordUsers (Name, DiscordId, LinkKey, Created, Active) values(?,?,?,datetime(),1)",Params)
    else:
        Log(f"Updating DiscordUsers register for Name: {member.name} - LinkKey: {Uid}",bcolors.OKBLUE,logging.INFO)
        DB.WriteDB(f"Update DiscordUsers set LinkKey = '{Uid}' where Id = {DUID}")
    sMessage = f"https://www.reddit.com/message/compose/?to=/r/argentina&subject=Discord%20Approval&message={Uid}"
    Log(f"Sending verification link to user {member.name} - {sMessage}",bcolors.OKBLUE,logging.INFO)
    await SendResponse([Message(True,True,MessageType.Text,f"Bienvenido al server de Discord de r/Argentina!\nClickea [aca]({sMessage}) y envia el mensaje para verificar tu usuario",member.id)], DB, None)
def CheckSender(author):
    Id = DB.GetDBValue(f"select Id from DiscordUsers where DiscordId = {author.id}")
    mRoles = DB.ExecuteDB("select R.Name " \
                        "from UserRoles UR " \
                        "join DiscordUsers D on D.Id = UR.DiscordId " \
                        "join Roles R on R.Id = UR.RoleId " \
                        f"where D.DiscordId = {author.id} ")
    Roles = []
    for Role in mRoles:
        Roles.append(Role[0])

    PendingAction = None
    if Id is not None:
        PendingAction = DB.GetDBValue(f"SELECT Id FROM Actions WHERE Mod = {Id} and ActionType is null and Processing is null and DiscordUserId is not null")
    return UserStatus(Id, Roles, PendingAction)

async def SendResponse(Response, DB, message):
    for IndResponse in Response:
        if IndResponse.To is None:
            destination = message.channel
        else:
            destination = await bot.fetch_user(IndResponse.To)
        asyncio.Task(HandleMessage(DiscordMaxChars,DB, destination,IndResponse))
        await asyncio.sleep(1)

async def PerformCycleActions():
    modmails = [LastModmailChecked(sSub.lower(),"") for sSub in DB.GetSetting("subreddit")]
    while True:
        try:
            for modmailbox in modmails:
                asyncio.Task(CheckModmail(modmailbox))
            asyncio.Task(CheckForUnmutedUsers())
            asyncio.Task(CheckForMutedUsers())
            asyncio.Task(ArchiveModmail())
            seconds = int(DB.GetSetting("RefreshModMail"))
            if seconds > 0:
                await asyncio.sleep(seconds)
        except:
            Log(f"Error at PerformCycleActions: {sys.exc_info()[1]}", bcolors.FAIL,logging.ERROR)
async def DiscordApproval(mail):
    try:
        await mail.load()
        Log(f"Verifying Reddit user {mail.user.name} through modmail. Modmail ID: {mail.id} - Message Content: {mail.messages[0].body_markdown}", bcolors.OKBLUE,logging.DEBUG)
        Uid = mail.messages[0].body_markdown[:36].replace("'","")
        RedditUser = mail.messages[0].author
        await RedditUser.load()
    except:
        Log(f"Error at reading DiscordApproval mail: {sys.exc_info()[1]}", bcolors.FAIL,logging.ERROR)
        await mail.read()
        await mail.archive()
        return
    RedditName = RedditUser.name
    RuId = DB.GetDBValue(f"select Id from RedditUsers where RedditName = '{RedditName}'") #get reddit user info
    if RuId is None:
        CakeDay = datetime.fromtimestamp(RedditUser.created).strftime('%Y-%m-%d')
        Params = (RedditName,CakeDay)
        Log(f"Creating new RedditUsers register RedditName: {RedditName} - CakeDay: {CakeDay}", bcolors.OKBLUE,logging.DEBUG)
        DB.WriteDB("Insert into RedditUsers (RedditName, CakeDay, Active) values(?,?,1)",Params)
        RuId = DB.GetDBValue(f"select Id from RedditUsers where RedditName = '{RedditName}'") #if we don't have it yet, create it
    DuId = DB.GetDBValue(f"select Id from DiscordUsers where LinkKey = '{Uid}'") #get discord user info (we should have it, since the user started the verification process somehow)
    if DuId is not None:
        try:
            LId = DB.GetDBValue(f"select Id from DiscordRedditUser where RedditId = {RuId} and DiscordId != {DuId}") 
            if LId is not None: #see if the user already registered this reddit account against other discord accounts
                #deregister the former user
                oDuId = DB.GetDBValue(f"select D.DiscordId from DiscordUsers D join DiscordRedditUser DRU on DRU.DiscordId = D.Id where DRU.Id = {LId}")
                Log(f"The reddit user {RedditUser} was linked to another Discord account: - DiscordUser.DiscordId: {oDuId}. Removing previous Discord Account from server to avoid duplicates...", bcolors.OKCYAN,logging.INFO)
                DiscordUser = await AssignDiscordRoleToUser(bot, oDuId, 'Usuario Verificado', False)
                if DiscordUser is None:
                    Log(f"Reddit user {RedditUser} was linked to another Discord account: - DiscordUser.DiscordId but this Discord account is not currently in the server", bcolors.OKCYAN,logging.INFO)
                    #await mail.read()
                    #await mail.archive()
                    #return
                else:
                    await DiscordUser.kick(reason="Demasiadas cuentas asignadas a un usuario de Reddit")
                DB.WriteDB(f"delete from DiscordRedditUser where Id = {LId}") #todo: esto deberia de quedar, no eliminar el link, asi contamos faltas previas del usuario de discord viejo tambien
            LId = DB.GetDBValue(f"select Id from DiscordRedditUser where DiscordId = {DuId} and RedditId = {RuId}")
            if LId is None:
                Params = (DuId,RuId)
                DB.WriteDB("Insert into DiscordRedditUser (DiscordId, RedditId, Created) values(?,?,datetime())",Params)
            DiscordId = DB.GetDBValue(f"select DiscordId from DiscordUsers where Id = {DuId}")
            
            Log(f"Assigning verified role and renaming Discord user {DiscordId} to user: {RedditName}", bcolors.OKBLUE,logging.DEBUG)
            DiscordUser = await AssignDiscordRoleToUser(bot, DiscordId, 'Usuario Verificado', True)
            if DiscordUser is not None:
                await DiscordUser.edit(nick = RedditName)
                DB.WriteDB(f"Update DiscordUsers set Name = '{RedditName}' where DiscordId = {DiscordId}")
                mBanDays = 0
                mBannedFrom = 0
                async for bannedrelationship in mail.owner.banned(redditor=RedditName):
                    mBannedFrom = bannedrelationship.date
                    mBanDays = bannedrelationship.days_left
                if mBanDays is not None and mBanDays > 0:
                    SaveDiscordMute(DB, datetime.fromtimestamp(bannedrelationship.date),mBanDays,DuId, None)
                    await AssignDiscordRoleToUser(bot, DiscordId, 'Mute', True)
                    await SendResponse([Message(False,True,MessageType.Text,f"Usuario verificado, tu usuario de reddit se encuentra banneado hasta dentro de {mBanDays} dias.\nNo podras participar del server hasta que se levante dicho ban.",DiscordId)], DB, None)
            else:
                Log(f"Couldn't assign verified role to Discord user {DiscordId} - User not found", bcolors.FAIL,logging.WARNING)
            await mail.read()
            await mail.archive()
        except:
            Log(f"Error whyle verifying Reddit User {RedditUser} - {sys.exc_info()[1]}",bcolors.WARNING, logging.ERROR)
    else:
        Log(f"Couldn't find Discord User for LinkKey {Uid}", bcolors.WARNING,logging.ERROR)

async def GetMailDetails(sub,ModmailId):
    mail = await sub.modmail(ModmailId)
    lstRetu = []
    await mail.load()
    for oMailMessage in mail.messages:
        sContent = oMailMessage.body_markdown
        lstRetu.append({'Id': mail.id,'Date': oMailMessage.date, 'Content': sContent, 'Author':oMailMessage.author.name})
    return lstRetu
async def HandleRespondedModmail(sub, row):
    MailDetails = await GetMailDetails(sub,row[2])
    mail = list(filter(lambda x: row[5] is None or x['Date'] > row[5],MailDetails))
    if len(mail) > 0:
        channel = await GetDMChannel(f"{row[0]}┃{row[4]}")
        if channel is not None:
            MsgHistory = await channel.history(limit=None, after=datetime.strptime(row[6], '%Y-%m-%d %H:%M:%S.%f')).flatten()
            if not any(x.author.id == bot.user.id for x in MsgHistory):
                embMsg = discord.Embed()
                embMsg.description  = f"{row[0]} Respondio al Modmail de reddit generado por:\n{row[3]}\n\n**Log**:\n{row[7]}\n\nResponde en este canal de forma anonima.\nLos mensajes que empiecen con '=' no seran enviados al usuario."
                await channel.send(row[1],embed=embMsg)
            for mMessage in mail:
                await channel.send(f"[{mMessage['Date']}] **{mMessage['Author']}**: {mMessage['Content']}")
            DB.WriteDB(f"Update Modmails set LastModmailUpdated = '{mail[len(mail) - 1]['Date']}' WHERE modmailID = '{row[2]}'")
async def CheckModmail(modmailbox):
    sub = await reddit.subreddit(modmailbox.Subreddit)
    sQuery = ""
    mlastUpd = ""
    try:
        async for mail in sub.modmail.conversations():
            if mail.last_updated > modmailbox.LastUpdated:
                if mail.subject.startswith('Discord Approval'):
                    asyncio.create_task(DiscordApproval(mail))
                elif mail.last_user_update is None or mail.last_mod_update is None or mail.last_mod_update < mail.last_user_update:
                    sQuery += f" or (MM.modmailID = '{mail.id}' and ifnull(a.LastModmailUpdated,'{mail.last_user_update}')  <= '{mail.last_user_update}')"
                if mail.last_updated > mlastUpd:
                    mlastUpd = mail.last_updated
    except:
        mlastUpd = modmailbox.LastUpdated
    if mlastUpd > modmailbox.LastUpdated:
        modmailbox.LastUpdated = mlastUpd
    if len(sQuery) > 0:
        sQuery =  "select R.Name, '<@' ||  m.DiscordID ||  '>', MM.modmailID, at.Description, a.Id, a.LastModmailUpdated, a.Date, a.Snapshot " \
                    "from Actions a join DiscordUsers R on R.Id = A.DiscordUserId join DiscordUsers m on m.Id = a.Mod join ActionType at on at.Id = a.ActionType join Modmails MM on MM.ActionId = A.Id " \
                    f"where not exists (select 1 from UserRoles UR join Roles RL on RL.Id = UR.RoleId where UR.DiscordId = m.Id and RL.Name = 'Reddit Mod') and {sQuery[4:]}"
        rows = DB.ExecuteDB(sQuery)
        for row in rows:
            asyncio.create_task(HandleRespondedModmail(sub, row))
async def CheckForUnmutedUsers():
    Users = DB.ExecuteDB(f"Select MU.Id, D.DiscordId from MutedUsers MU join DiscordUsers D on D.Id = MU.DiscordId where [To] < {datetime.timestamp(datetime.now())} and Performed is null")
    for user in Users:
        await AssignDiscordRoleToUser(bot, user[1], 'Mute',False)
        DB.WriteDB(f"Update MutedUsers set Performed = 1 where Id = {user[0]}")
async def CheckForMutedUsers():
    Users = DB.ExecuteDB(f"Select MU.Id, MU.DiscordId, MU.ActionID from MutedUsers MU where [To] > {datetime.timestamp(datetime.now())} and Performed = 0")
    for user in Users:
        ActionDetailRow = GetCommonActionDetail(DB, "ActionId",user[2])
        if ActionDetailRow is not None:
            ApplyingPol = GetCurrentPolicy(user[1])
            modmail = await CreateModMail(ApplyingPol['Message'], ActionDetailRow['Link'],ActionDetailRow['TypeDesc'],ActionDetailRow['Details'],ActionDetailRow['User'],ActionDetailRow['RuleLink'], ActionDetailRow['Snapshot'],reddit, DB)
            await NotifyDiscordUser(DB, bot,{'ActionDetailRow': ActionDetailRow, 'ModMail': modmail},ApplyingPol,user[2])
            DB.WriteDB(f'update MutedUsers set Performed = null where ActionID = {user[2]};')
        else:
            DB.WriteDB(f'delete from MutedUsers where ActionID = {user[2]};')
async def AssignDiscordRoleToUser(bot, DiscordId, RoleName, assign):
    DiscordServer = bot.get_guild(int(os.getenv('DiscordServer')))
    DiscordUser = DiscordServer.get_member(DiscordId)
    if DiscordUser is None:
        return None
    if len(RoleName) > 0:
        Role = discord.utils.get(DiscordServer.roles, name = RoleName)
        if assign:
            await DiscordUser.add_roles(Role)
        else:
            await DiscordUser.remove_roles(Role)
    return DiscordUser
async def NotifyDiscordUser(DB, bot, preparedAction, ApplyingPol, ActionId):
    ActionDetailRow = preparedAction["ActionDetailRow"]
    modmail = preparedAction["ModMail"]
    sRole = ''
    oQueryResult = DB.ExecuteDB(f"Select Id, DiscordId from DiscordUsers where Name = '{ActionDetailRow['User']}'")
    if len(oQueryResult) > 0:
        UserData = oQueryResult[0]
        if ApplyingPol['Action'] == 2:
            sRole = 'Mute'
            EditRow = DB.GetDBValue(f"select ID from MutedUsers where DiscordId = {UserData[0]} and [To] > {datetime.timestamp(datetime.now())}")
            if EditRow is None:
                Params = (UserData[0], datetime.timestamp(datetime.now()), datetime.timestamp(datetime.now() + relativedelta(days=+int(ApplyingPol['BanDays']))))
                DB.WriteDB("Insert into MutedUsers (DiscordId, [From], [To]) values(?,?,?);",Params)
            else:
                DB.WriteDB(f"Update MutedUsers set Performed = null, [To] = {datetime.timestamp(datetime.now() + relativedelta(days=+int(ApplyingPol['BanDays'])))} where Id = {EditRow};")
            if ApplyingPol['BanDays'] == -1:
                sMuteMSG = "**Has sido Muteado de forma permanente en Discord.**\n\nAun podras ver los mensajes del server pero no podras participar."
                sResp = "Usuario muteado de forma permanente"
            else:
                sMuteMSG = f"**Has sido Temporalmente Muteado en Discord.**\n\nEste mute durara {ApplyingPol['BanDays']} dias. Aun podras ver los mensajes del server pero no podras participar."
                sResp = f"Usuario muteado por {ApplyingPol['BanDays']} dias"
            preparedAction["ModMail"] = f"{sMuteMSG}\n\n{preparedAction['ModMail']}"
        else:
            sResp = "Usuario advertido."
        DiscordUser = await AssignDiscordRoleToUser(bot, UserData[1], sRole, True)
        await SendResponse([Message(True,True,MessageType.Text,preparedAction["ModMail"] +"\nSi queres consultar por esta medida responde a este mensaje.",DiscordUser.id)], DB, None)
        return sResp

#client.run(TOKEN)
bot.run(TOKEN)