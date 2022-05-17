import discord
import asyncio
class MessageType:
    Text = 1
    Image = 2
class Recipient:
    Channel = 1
    User = 2
class Message:
    def __init__(self,Embed, NoDel, Type, Content, To = Recipient.Channel):
        self.Embed = Embed
        self.NoDel = NoDel
        self.Type = Type
        self.Content = Content
        self.To = To

async def HandleMessage(DiscordMaxChars, DB, message, Response):
    Msgs = []
    bEmbed = False
    if Response.Type == MessageType.Text:
        for indRes in Sectionize(DiscordMaxChars, Response.Content, "--------------------", True):
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
async def HandleDirectMessage(DiscordMaxChars, DB, client, user, Response):
    Msgs = []
    bEmbed = False
    if Response.Type == MessageType.Text:
        for indRes in Sectionize(DiscordMaxChars, Response.Content, "--------------------", True):
            if Response.Embed:
                embMsg = discord.Embed()
                embMsg.description = indRes
                sentMsg = await user.send(user, embed=embMsg)
            else:
                sentMsg = await user.send(user, indRes)
            Msgs.append(sentMsg)
    elif Response.Type == MessageType.Image:
        sentMsg = await user.send(user, file=discord.File(Response.Content))
        Msgs.append(sentMsg)
    seconds = int(DB.GetSetting("DelMsgAfterSeconds"))
    if seconds > 0 and not Response.NoDel:
        await asyncio.sleep(seconds)
        for Msg in Msgs:
            await Msg.delete()
def CutStringInPieces(chunk, Max, retChunks):
    while len(chunk) > Max:
        retChunks.append(chunk[:Max])
        chunk = chunk[Max:]
    retChunks.append(chunk)
def Sectionize(Max, sIn, sSplit, UseNewLinesForChunks):
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
                        spaceChunks = Sectionize(Max,chunk,"\n",False)
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