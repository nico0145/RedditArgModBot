BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS "Settings" (
	"Id"	INTEGER NOT NULL,
	"Key"	text NOT NULL,
	"Value"	text NOT NULL,
	"DataType"	text NOT NULL,
	PRIMARY KEY("Id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "Policies" (
	"Id"	INTEGER NOT NULL,
	"From"	bigint NOT NULL,
	"To"	bigint NOT NULL,
	"Action"	bigint NOT NULL,
	"BanDays"	bigint,
	"Message"	text NOT NULL,
	PRIMARY KEY("Id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "ActionType" (
	"Id"	INTEGER NOT NULL,
	"Description"	text NOT NULL,
	"Weight"	bigint NOT NULL,
	"Active"	bit NOT NULL,
	"DefaultMessage"	TEXT,
	PRIMARY KEY("Id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "PassFilterUser" (
	"Id"	INTEGER NOT NULL,
	"User"	TEXT NOT NULL,
	"Date"	TEXT NOT NULL,
	PRIMARY KEY("Id")
);
CREATE TABLE IF NOT EXISTS "ModLog" (
	"Id"	INTEGER NOT NULL UNIQUE,
	"Action"	TEXT,
	"Date"	TEXT,
	"Description"	TEXT,
	"ModName"	TEXT,
	"Author"	TEXT,
	"Permalink"	TEXT,
	PRIMARY KEY("Id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "ScheduledPosts" (
	"Id"	INTEGER NOT NULL UNIQUE,
	"RedditID"	INTEGER,
	"PostedDate"	TEXT,
	"PostID"	TEXT,
	"IsStickied"	INTEGER,
	PRIMARY KEY("Id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "RedditUsers" (
	"Id"	INTEGER NOT NULL,
	"RedditName"	TEXT,
	"CakeDay"	TEXT,
	"Active"	INTEGER,
	PRIMARY KEY("Id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "Roles" (
	"Id"	INTEGER NOT NULL,
	"Name"	INTEGER NOT NULL,
	PRIMARY KEY("Id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "UserRoles" (
	"Id"	INTEGER NOT NULL,
	"DiscordId"	INTEGER NOT NULL,
	"RoleId"	INTEGER NOT NULL,
	PRIMARY KEY("Id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "DiscordUsers" (
	"Id"	INTEGER NOT NULL,
	"Name"	TEXT,
	"DiscordId"	NUMERIC,
	"TimeZone"	TEXT,
	"LinkKey"	TEXT,
	"Created"	TEXT,
	"Active"	INTEGER,
	PRIMARY KEY("Id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "DiscordRedditUser" (
	"Id"	INTEGER NOT NULL,
	"DiscordId"	INTEGER NOT NULL,
	"RedditId"	INTEGER NOT NULL,
	"Created"	TEXT NOT NULL,
	PRIMARY KEY("Id" AUTOINCREMENT)
);
CREATE TABLE IF NOT EXISTS "Actions" (
	"Id"	INTEGER NOT NULL,
	"User"	text NOT NULL,
	"ActionType"	bigint,
	"Link"	text NOT NULL,
	"Mod"	bigint NOT NULL,
	"Date"	text NOT NULL,
	"Description"	text,
	"LastModmailUpdated"	text,
	"modmailID"	text,
	"Snapshot"	TEXT,
	"Processing"	INTEGER,
	PRIMARY KEY("Id" AUTOINCREMENT)
);
INSERT INTO "Settings" VALUES (1,'subreddit','Argentina','str');
INSERT INTO "Settings" VALUES (2,'warnexpires','180','int');
INSERT INTO "Settings" VALUES (3,'DelMsgAfterSeconds','120','int');
INSERT INTO "Settings" VALUES (4,'RefreshModMail','50','int');
INSERT INTO "Settings" VALUES (5,'GaryChannel','870268863659540531','int');
INSERT INTO "Settings" VALUES (6,'PostsFiltroAutomod','15','int');
INSERT INTO "Settings" VALUES (7,'PuntosUsuarioProblematico','7','int');
INSERT INTO "Settings" VALUES (8,'HusoHorarioDB','1','int');
INSERT INTO "Settings" VALUES (9,'ChatbotCommandSymbol','!','str');
INSERT INTO "Roles" VALUES (1,'Reddit Mod');
INSERT INTO "Roles" VALUES (2,'Bot User');
INSERT INTO "Roles" VALUES (3,'Bot Config');
INSERT INTO "Roles" VALUES (4,'Admin');
INSERT INTO "Roles" VALUES (5,'Discord Mod');
COMMIT;
