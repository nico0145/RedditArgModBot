-- Script Date: 12/7/2021 6:33 PM  - ErikEJ.SqlCeScripting version 3.5.2.87
-- Database information:
-- Database: C:\Users\Nicolas\Desktop\Startup\my-test.db
-- ServerVersion: 3.32.1
-- DatabaseSize: 388 KB
-- Created: 22/4/2021 4:40 PM

-- User Table information:
-- Number of tables: 5
-- Actions: -1 row(s)
-- ActionType: -1 row(s)
-- Moderators: -1 row(s)
-- Policies: -1 row(s)
-- Settings: -1 row(s)

SELECT 1;
PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE [Settings] (
  [Id] INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, [Key] text NOT NULL
, [Value] text NOT NULL
, [DataType] text NOT NULL
);
CREATE TABLE [Policies] (
  [Id] INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, [From] bigint NOT NULL
, [To] bigint NOT NULL
, [Action] bigint NOT NULL
, [BanDays] bigint NULL
, [Message] text NOT NULL
);
CREATE TABLE [Moderators] (
  [Id] INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, [Name] text NOT NULL
, [RedditName] text NOT NULL
, [DiscordID] numeric(53,0) NOT NULL
, [IsAdmin] bit NULL
);
CREATE TABLE [ActionType] (
  [Id] INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, [Description] text NOT NULL
, [Weight] bigint NOT NULL
, [Active] bit NOT NULL
);
CREATE TABLE [Actions] (
  [Id] INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL
, [User] text NOT NULL
, [ActionType] bigint NULL
, [Link] text NOT NULL
, [Mod] bigint NOT NULL
, [Date] text NOT NULL
, [Description] text NULL
, [LastModmailUpdated] text NULL
, [modmailID] text NULL
);
INSERT INTO [Settings] ([Id],[Key],[Value],[DataType]) VALUES (
1,'subreddit','Argentina','str');
INSERT INTO [Settings] ([Id],[Key],[Value],[DataType]) VALUES (
2,'warnexpires','180','int');
INSERT INTO [Settings] ([Id],[Key],[Value],[DataType]) VALUES (
3,'DelMsgAfterSeconds','120','int');
INSERT INTO [Settings] ([Id],[Key],[Value],[DataType]) VALUES (
4,'RefreshModMail','60','int');
INSERT INTO [Settings] ([Id],[Key],[Value],[DataType]) VALUES (
5,'GaryChannel','821518583209263115','int');
INSERT INTO [Policies] ([Id],[From],[To],[Action],[BanDays],[Message]) VALUES (
1,1,5,1,-1,'Esta es una advertencia por tu post o comentario en /r/[Sub].\n\n\n\n**Nota de los moderadores:**\n\n>[Details]\n\n\n\n**Ultimas de faltas del usuario**\n\n[Summary]');
INSERT INTO [Policies] ([Id],[From],[To],[Action],[BanDays],[Message]) VALUES (
2,6,10,2,2,'**Nota de los moderadores:**\n\n>[Details]\n\n**Ultimas de faltas del usuario**\n\n[Summary]');
INSERT INTO [Policies] ([Id],[From],[To],[Action],[BanDays],[Message]) VALUES (
3,11,15,2,5,'**Nota de los moderadores:**\n\n>[Details]\n\n**Ultimas de faltas del usuario**\n\n[Summary]');
INSERT INTO [Policies] ([Id],[From],[To],[Action],[BanDays],[Message]) VALUES (
4,16,30,2,30,'**Nota de los moderadores:**\n\n>[Details]\n\n**Ultimas de faltas del usuario**\n\n[Summary]');
INSERT INTO [Policies] ([Id],[From],[To],[Action],[BanDays],[Message]) VALUES (
5,31,9999,2,-1,'**Nota de los moderadores:**\n\n>[Details]\n\n**Ultimas de faltas del usuario**\n\n[Summary]');
INSERT INTO [Policies] ([Id],[From],[To],[Action],[BanDays],[Message]) VALUES (
6,0,0,1,-1,'El siguiente post/comentario ha sido removido por los moderadores de /r/[Sub].\n\n\n\n[Link]\n\n\n\n**Motivo:** [ActionTypeDesc]\n\n\n\n**Nota de los moderadores:** [Details]');
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
1,' El contenido debe ser relacionado a Argentina.',1,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
2,'No se permiten los ataques personales.',1,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
3,'No se permite el racismo, xenofobia u otras expresiones de odio.',4,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
4,'Bajadas de linea',1,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
5,'Artículos periodísticos y Tweets',0,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
6,'Off-topic',1,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
7,'Editorialización de contenido',0,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
8,'Capturas de redes sociales o chats.',0,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
9,'Novelty accounts, bots y evasión de bans',32,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
10,'Rants en contra del subreddit y sugerencias.',2,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
11,'Spam, Blogspam y reposts',0,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
12,'No se permiten spoilers',2,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
13,'No se aceptan mendigos de steam/we don''t accept steam beggars',40,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
14,'Threatening, harassing, or inciting violence',2,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
15,'Personal and confidential information',40,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
16,'No se permiten los ataques personales.',6,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
17,'No está permitida la autopromoción',31,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
18,'Rants en contra del subreddit y sugerencias.',12,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
19,' El contenido debe ser relacionado a Argentina.',0,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
23,'Off-topic',0,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
25,'Low Effort',0,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
26,'Tu post corresponde al thread diario de preguntas ',0,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
29,'Las consultas de Moderación se hacen únicamente por DM, por favor responde a este mensaje',0,1);
INSERT INTO [ActionType] ([Id],[Description],[Weight],[Active]) VALUES (
30,' Spam, Blogspam y reposts',1,1);
COMMIT;
