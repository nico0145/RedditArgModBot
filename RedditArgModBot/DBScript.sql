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
CREATE TABLE "Moderators" (
	"Id"	INTEGER NOT NULL,
	"Name"	text NOT NULL,
	"RedditName"	text NOT NULL,
	"DiscordID"	numeric(53, 0) NOT NULL,
	"IsAdmin"	bit,
	"Active"	bit,
	"TimeZone"	TEXT,
	PRIMARY KEY("Id" AUTOINCREMENT)
);
CREATE TABLE [ActionType] ( 
  [Id] INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL 
, [Description] text NOT NULL 
, [Weight] bigint NOT NULL 
, [Active] bit not null 
, [DefaultMessage] TEXT NULL);
CREATE TABLE [Actions] ( 
  [Id] INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL 
, [User] text NOT NULL 
, [ActionType] bigint NULL 
, [Link] text NOT NULL 
, [Mod] bigint NOT NULL 
, [Date] text NOT NULL 
, [Description] text NULL 
, [LastModmailUpdated] text NULL, [modmailID] text NULL);
CREATE TABLE "ModLog" (
	"Id"	INTEGER NOT NULL UNIQUE,
	"Action"	TEXT,
	"Date"	TEXT,
	"Description"	TEXT,
	"ModName"	TEXT,
	"Author"	TEXT,
	"Permalink"	TEXT,
	PRIMARY KEY("Id" AUTOINCREMENT)
);
CREATE TABLE "PassFilterUser" (
	"Id"	INTEGER NOT NULL,
	"User"	TEXT NOT NULL,
	"Date"	TEXT NOT NULL,
	PRIMARY KEY("Id")
);
CREATE TABLE "ScheduledPosts" (
	"Id"	INTEGER NOT NULL UNIQUE,
	"RedditID"	INTEGER,
	"PostedDate"	TEXT,
	"PostID"	TEXT,
	"IsStickied"	INTEGER,
	PRIMARY KEY("Id" AUTOINCREMENT)
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
INSERT INTO [Settings] ([Id],[Key],[Value],[DataType]) VALUES (
6,'PostsFiltroAutomod','30','int');
INSERT INTO [Settings] ([Id],[Key],[Value],[DataType]) VALUES (
7,'PuntosUsuarioProblematico','7','int');
INSERT INTO [Settings] ([Id],[Key],[Value],[DataType]) VALUES (
8,'HusoHorarioDB','1','int');
COMMIT;
