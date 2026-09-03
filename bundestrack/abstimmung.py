import utility
from pathlib import Path
import pandas as pd

class NamentlicheAbstimmung:
    def __init__(self, datapath, period, start, end):
        files = utility.list_files(datapath / f"{period}" / "abstimmungen")
        range_files = utility.subset_files(files, start, end)

        self.members, self.fractions = self.get_members(datapath, period) # get all members of the bundestag
        self.altnames = self.get_altnames(datapath, period) # alternative names
        self.abstimmung_dfs = []

        for votefile in range_files:
            print(votefile)
            votes_df = pd.read_excel(votefile)
            votes_df = votes_df[[
                "Fraktion/Gruppe", "Name", "Vorname", "ja", "nein", "Enthaltung", "ungültig", "nichtabgegeben"
            ]]

            # combine where fraction is Die Linke or DIE LINKE.
            votes_df["Fraktion/Gruppe"] = votes_df["Fraktion/Gruppe"].replace("DIE LINKE.", "Die Linke")
            # if alternative name exists, replace
            votes_df[["Vorname", "Name"]] = votes_df[["Vorname","Name"]].apply(lambda x: self.map_altnames(x["Vorname"], x["Name"]), axis=1, result_type='expand')
            votes_df["Fraktion/Gruppe"] = votes_df[["Vorname", "Name"]].apply(lambda x: self.members[(x["Vorname"], x["Name"])], axis=1)

            self.abstimmung_dfs.append(votes_df)

        #merge
        self.abstimmung_df = pd.concat(self.abstimmung_dfs, ignore_index=True)
        membervotes = self.abstimmung_df.groupby(
            ["Fraktion/Gruppe", "Vorname", "Name"]
        )[["ja", "nein", "Enthaltung", "ungültig", "nichtabgegeben"]].sum().reset_index()
        membervotes = membervotes.sort_values("nichtabgegeben", ascending=True) # sort by nichtabgegeben descending
        # count ja nein Enthaltung ungültig nichtabgegeben and add to new column
        membervotes["total_votes"] = membervotes["ja"] +  membervotes["nein"] + membervotes["Enthaltung"] + membervotes["ungültig"] + membervotes["nichtabgegeben"]
        membervotes["ratio_ja"] = membervotes["ja"] / membervotes["total_votes"]
        membervotes["ratio_nein"] = membervotes["nein"] / membervotes["total_votes"]
        membervotes["ratio_Enthaltung"] = membervotes["Enthaltung"] / membervotes["total_votes"]
        membervotes["ratio_ungültig"] = membervotes["ungültig"] / membervotes["total_votes"]
        membervotes["ratio_nichtabgegeben"] = membervotes["nichtabgegeben"] / membervotes["total_votes"]

        print(membervotes.to_string())
        # save to file
        membervotes.to_csv(datapath / f"{period}" / "membervotes.csv", index=False)

    def get_members(self, datapath, period):
        abgeordnete = {}
        fractions = []
        fh = open(datapath / f"{period}" / "abgeordneten.txt")
        for line in fh:
            parts = line.rstrip().split("\t")
            abgeordnete[(parts[0],parts[1])] = parts[2]
            if parts[2] not in fractions:
                fractions.append(parts[2])
        return abgeordnete, fractions

    def get_altnames(self, datapath, period):
        altnames = {}
        fh = open(datapath / f"{period}" / "altnames.txt")
        for line in fh:
            parts = line.rstrip().split("\t")
            altnames[(parts[0],parts[1])] = (parts[2], parts[3])
        return altnames

    def map_altnames(self, vorname, name):
        if (vorname, name) in self.altnames:
            return self.altnames[(vorname, name)]
        else:
            return (vorname, name)
