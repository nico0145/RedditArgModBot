import os
import discord
import uuid
from dotenv import load_dotenv
from DBHandle import *
from DiscordHandle import *
from StaticHelpers import *
load_dotenv()
TOKEN = os.getenv('DiscordChatmodToken')
intents = discord.Intents.all()
client = discord.Client(intents=intents)
DB = DBHandle(os.getenv('DB'))


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

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    Response = None
    CommandSymbol = DB.GetSetting('ChatbotCommandSymbol')
    StandardMessage =  message.content.lower().strip(' ')
    if StandardMessage == f"{CommandSymbol}ayuda":
        Response = [Message(False,False,MessageType.Text,f"{CommandSymbol}ayuda - Muestra esta ayuda\n")]
    elif StandardMessage == f"{CommandSymbol}test":
        Response = [Message(False,False,MessageType.Text,"Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo. Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit, sed quia consequuntur magni dolores eos qui ratione voluptatem sequi nesciunt. Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet, consectetur, adipisci velit, sed quia non numquam eius modi tempora incidunt ut labore et dolore magnam aliquam quaerat voluptatem. Ut enim ad minima veniam, quis nostrum exercitationem ullam corporis suscipit laboriosam, nisi ut aliquid ex ea commodi consequatur? Quis autem vel eum iure reprehenderit qui in ea voluptate velit esse quam nihil molestiae consequatur, vel illum qui dolorem eum fugiat quo voluptas nulla pariatur?Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo. Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit, sed quia consequuntur magni dolores eos qui ratione voluptatem sequi nesciunt. Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet, consectetur, adipisci velit, sed quia non numquam eius modi tempora incidunt ut labore et dolore magnam aliquam quaerat voluptatem. Ut enim ad minima veniam, quis nostrum exercitationem ullam corporis suscipit laboriosam, nisi ut aliquid ex ea commodi consequatur? Quis autem vel eum iure reprehenderit qui in ea voluptate velit esse quam nihil molestiae consequatur, vel illum qui dolorem eum fugiat quo voluptas nulla pariatur?Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo. Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit, sed quia consequuntur magni dolores eos qui ratione voluptatem sequi nesciunt. Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet, consectetur, adipisci velit, sed quia non numquam eius modi tempora incidunt ut labore et dolore magnam aliquam quaerat voluptatem. Ut enim ad minima veniam, quis nostrum exercitationem ullam corporis suscipit laboriosam, nisi ut aliquid ex ea commodi consequatur? Quis autem vel eum iure reprehenderit qui in ea voluptate velit esse quam nihil molestiae consequatur, vel illum qui dolorem eum fugiat quo voluptas nulla pariatur?")]
    elif StandardMessage == f"{CommandSymbol}verificar":
        DUID = DB.GetDBValue(f"select Id from DiscordUsers where DiscordId = {message.author.id}")
        Uid = uuid.uuid4()
        if DUID is None:
            Params = (message.author.name, message.author.id, Uid)
            DB.WriteDB("Insert into DiscordUsers (Name, DiscordId, LinkKey, Created, Active) values(?,?,?,datetime(),1)",Params)
        else:
            DB.WriteDB(f"Update DiscordUsers set LinkKey = '{Uid}' where Id = {DUID}")
            Uid = DB.GetDBValue(f"select LinkKey from DiscordUsers where Id = {DUID}")
        sMessage = f"https://www.reddit.com/message/compose/?to=/r/argentina&subject=Discord%20Approval&message={Uid}"
        Response = [Message(True,True,MessageType.Text,f"Clickea [aca]({sMessage}) y envia el mensaje para verificar tu usuario",Recipient.User)]
    for IndResponse in Response:
            if IndResponse.To == Recipient.Channel:
                asyncio.Task(HandleMessage(int(os.getenv('DiscordMaxChars')),DB, message,IndResponse))
            else:
                asyncio.Task(HandleDirectMessage(int(os.getenv('DiscordMaxChars')),DB, client, message.author,IndResponse))
            await asyncio.sleep(1)

async def CheckModmail():
    while True:
        try:
            seconds = int(DB.GetSetting("RefreshModMail"))
            if seconds > 0:
                await asyncio.sleep(seconds)
            sub = await reddit.subreddit(DB.GetSetting("subreddit"))
            async for mail in sub.modmail.conversations(sort="unread"):
                if mail.subject == 'Discord Approval':
                    await mail.load()
                    Uid = mail.messages[0].body_markdown
                    RedditUser = mail.messages[0].author
                    await RedditUser.load()
                    RedditName = RedditUser.name
                    RuId = DB.GetDBValue(f"select Id from RedditUsers where RedditName = '{RedditName}'")
                    if RuId is None:
                        CakeDay = datetime.fromtimestamp(RedditUser.created).strftime('%Y-%m-%d')
                        Params = (RedditName,CakeDay)
                        DB.WriteDB("Insert into RedditUsers (RedditName, CakeDay, Active) values(?,?,1)",Params)
                        RuId = DB.GetDBValue(f"select Id from RedditUsers where RedditName = '{RedditName}'")
                    DuId = DB.GetDBValue(f"select Id from DiscordUsers where LinkKey = '{Uid}'")
                    if DuId is not None:
                        LId = DB.GetDBValue(f"select Id from DiscordRedditUser where DiscordId = {DuId} and RedditId = {RuId}")
                        if LId is None:
                            Params = (DuId,RuId)
                            DB.WriteDB("Insert into DiscordRedditUser (DiscordId, RedditId, Created) values(?,?,datetime())",Params)
                        DiscordId = DB.GetDBValue(f"select DiscordId from DiscordUsers where Id = {DuId}")
                        DiscordServer = client.get_guild(int(os.getenv('DiscordServer')))
                        DiscordUser = DiscordServer.get_member(DiscordId)
                        VerifRole = discord.utils.get(DiscordServer.roles, name = 'Usuario Verificado')
                        await DiscordUser.add_roles(VerifRole)
                        #At this point both user tables are filled and the relationship table too, it's time to add the discord role
                    await mail.read()
                    await mail.archive()
        except:
            print(f"Ocurrio un error al intentar obtener modmails de la API de Reddit: {sys.exc_info()[1]}")
client.run(TOKEN)