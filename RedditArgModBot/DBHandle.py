import sqlite3 as sl
DBPath = ""
class DBHandle(object):
    def __init__(self, mDBPath):
        self.DBPath = mDBPath
    def openDB(self):
        return sl.connect(self.DBPath,15)
    def ExecuteDB(self, query):
        DB = self.openDB();
        oRet = self.GetDBValues(DB, query)
        DB.close()
        return oRet
    def WriteDB(self, query, params = None):
        DB = self.openDB();
        if params == None:
            DB.execute(query)
        else:
            DB.execute(query, params)
        DB.commit()
        DB.close()
    def GetDBValues(self, DB, query):
        cur = DB.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        cur.close()
        return rows
    def GetDBValue(self, query):
        return self.ExecuteDB(query)[0][0]
    def GetSetting(self, setting, ModId = 0):
        return self.GetDBValue(f"SELECT [Value] FROM Settings where [Key] = '{setting}'")
    def GetTable(self, sQuery):
        DB = self.openDB();
        cur = DB.cursor()
        cur.execute(sQuery)
        oRet = self.GetTableFormat(cur)
        DB.close()
        return oRet
    def GetTableFormat(self, cur):
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