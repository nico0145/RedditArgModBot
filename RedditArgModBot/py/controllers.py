#!/usr/bin/env python
import sys
import os
import os.path
from dotenv import load_dotenv
import dotenv
from py.StaticHelpers import *
import cherrypy
from tornado import web,template
import asyncpraw
import sys
import asyncio
from py.DBHandle import *
loader = template.Loader('..\\resources')
load_dotenv()
# Authorise an user to access reddit
app_key = os.getenv('app_key')
app_secret = os.getenv('app_secret')
DB = DBHandle(os.getenv('DB'))
class Root():
    @cherrypy.expose
    def default(self, *args, **kwargs):
        out = ''
        for key, value in kwargs.items():
            out += key + '=' + value + '\n'
            cherrypy.session[key] = value

        #you'll also need to store a value in session
        cherrypy.session['Token'] = ""
        #print(cherrypy.session.id)
        return out
    @cherrypy.expose
    def index(self, *args, **kwargs):    
        checkLoginStatus(args, kwargs)
        tmpl = loader.load('index.html')
        listProcess = getProcessStatus()
        return tmpl.generate(username = cherrypy.session['RedditUser'], listProcess=listProcess)
    @cherrypy.expose
    def unauthorized(self, *args, **kwargs):    
        tmpl = loader.load('unauthorized.html')
        return tmpl.generate(username = cherrypy.session['RedditUser'])
    @cherrypy.expose
    def logoff(self, *args, **kwargs):    
        tmpl = loader.load('logoff.html')
        sUser = cherrypy.session['RedditUser']
        cherrypy.session.clear()
        return tmpl.generate(username = sUser)
    @cherrypy.expose
    def logs(self, *args, **kwargs):    
        checkLoginStatus(args, kwargs)
        tmpl = loader.load('logs.html')
        logFileNames = ['AutomodLog','RedditBotLog','DiscordBotLog','WebInterfaceLog']
        if kwargs.get('log-names') is not None and kwargs['log-names'] != "":
            logFile = open(os.getenv(kwargs['log-names']), 'r', encoding='utf8', errors='ignore')
            lines = logFile.readlines()
            logOutput = lines[int(kwargs['registerAmt']) * -1:]
            logFile.close()
        else:
            logOutput = []
        return tmpl.generate(logFiles=logFileNames, logLines = logOutput)
    @cherrypy.expose
    def submit(self, cancel = False, **value):
        if cherrypy.request.method == 'POST':
            if cancel:
                raise cherrypy.HTTPRedirect('/') # to cancel the action
            link = Link(**value)
            self.data[link.id] = link
            raise cherrypy.HTTPRedirect('/')
        tmp = loader.load('submit.html')
        streamValue = tmp.generate()

        return streamValue

def GetDefaultRedditObj():
    rres = executeAsync(async_get_default_reddit_object('http://robotina.sytes.net',"Reddit Mod Bot Web Interface"))
    if rres['status'] == 'success':
        return rres['data']
    return None
def AuthorizeToken(reddit, code):
    return executeAsync(reddit.auth.authorize(code))

def executeAsync(task):
    try:
        loop = asyncio.get_event_loop()
    except:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return  loop.run_until_complete(task)
    #loop = asyncio.new_event_loop()
    #asyncio.set_event_loop(loop)
    #send_fut = asyncio.run_coroutine_threadsafe(task, loop)
    #return send_fut.result()
def checkLoginStatus(args, kwargs):
    if cherrypy.session.get("Token") is None:
        reddit = GetDefaultRedditObj()
        if reddit is not None:
            if kwargs.get("code") is not None:
                RefreshToken = AuthorizeToken(reddit, kwargs['code'])
                redditUser = executeAsync(reddit.user.me())
                if redditUser is not None:
                    cherrypy.session['Token'] = RefreshToken
                    cherrypy.session['RedditUser'] = redditUser.name
                    cherrypy.session['Roles'] = getUserRoles(redditUser.name)
            else:
                redditScopes = ["identity"]#["account", "identity", "read"]
                redditUrl = reddit.auth.url(redditScopes, cherrypy.session.id, 'permanent')
                raise cherrypy.HTTPRedirect(redditUrl)
    if cherrypy.session.get("Roles") is not None and len(cherrypy.session['Roles']) == 0:
        raise cherrypy.HTTPRedirect('unauthorized')

def getUserRoles(redditUserName):
    mRoles = DB.ExecuteDB("select R.Name " \
                        "from UserRoles UR " \
                        "join DiscordRedditUser D on D.DiscordId = UR.DiscordId " \
                        "join Roles R on R.Id = UR.RoleId " \
                        "join RedditUsers RU on RU.Id = D.RedditId " \
                        f"where RU.RedditName = '{redditUserName}' ")
    Roles = []
    for Role in mRoles:
        Roles.append(Role[0])
    return Roles

def main(filename):
    current_dir = os.path.dirname(os.path.abspath(__file__)) + os.path.sep
    config = {
        'global': {
            'tools.encode.on': True, 'tools.encode.encoding': 'utf-8',
            'tools.decode.on': True,
            'tools.trailing_slash.on': True,
            'tools.sessions.on': True,
            'tools.sessions.storage_type': "File",
            'tools.sessions.storage_path': '..\\sessions',
            'tools.sessions.timeout': 10,
            'server.socket_port': 80,
            'server.socket_host': '0.0.0.0',
            'log.screen': None
        },
        '/':{
            'tools.staticdir.root': current_dir,
        },
        '/css': {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': '..\\resources\\static\\css'
        }
    }
    InitializeLog(os.getenv('WebInterfaceLog'))
    envFile = os.path.join(current_dir, '.env')
    dotenv.set_key(envFile,"WebIFPID",str(os.getpid()))
    cherrypy.quickstart(Root(), '/', config)
if __name__ == '__main__':
    main(sys.argv[0])