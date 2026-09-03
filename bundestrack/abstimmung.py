import json
import utility
from pathlib import Path
import pandas as pd

def write_csv_with_comment(df, path, comment_lines):
    with open(path, "w", newline="") as f:
        for line in comment_lines:
            f.write(f"# {line}\n")
        df.to_csv(f, index=False, sep=";")


class NamentlicheAbstimmung:
    def __init__(self, datapath, period, start, end, docs_path=Path("docs/data")):
        files = utility.list_files(datapath / f"{period}" / "abstimmungen")
        range_files = utility.subset_files(files, start, end)
        self.docs_path = docs_path / f"{period}"
        self.docs_path.mkdir(parents=True, exist_ok=True)

        self.members, self.fractions = self.get_members(datapath, period) # get all members of the bundestag
        self.altnames = self.get_altnames(datapath, period) # alternative names
        self.abstimmung_dfs = []
        sitzverteilung_per_vote = {} # fraction sizes can shift within a period (defections, departures, ...)

        for votefile in range_files:
            print(votefile)
            votes_df = pd.read_excel(votefile)
            votes_df = votes_df[[
                "Fraktion/Gruppe", "Name", "Vorname", "ja", "nein", "Enthaltung", "ungültig", "nichtabgegeben"
            ]]

            # combine where fraction is Die Linke or DIE LINKE.
            votes_df["Fraktion/Gruppe"] = votes_df["Fraktion/Gruppe"].replace("DIE LINKE.", "Die Linke")
            vote_date = votefile.name.split("_")[0]
            sitzverteilung_per_vote[vote_date] = votes_df["Fraktion/Gruppe"].value_counts()
            votes_df["date"] = vote_date
            # party as recorded at the time of this vote - a member who switches fraction may
            # start voting with their new fraction, so their historical votes must stay with
            # whichever fraction they belonged to on that day, not their current/final one
            votes_df["Fraktion_bei_Abstimmung"] = votes_df["Fraktion/Gruppe"]

            # if alternative name exists, replace
            votes_df[["Vorname", "Name"]] = votes_df[["Vorname","Name"]].apply(lambda x: self.map_altnames(x["Vorname"], x["Name"]), axis=1, result_type='expand')
            votes_df["Fraktion/Gruppe"] = votes_df[["Vorname", "Name"]].apply(lambda x: self.members[(x["Vorname"], x["Name"])], axis=1)

            self.abstimmung_dfs.append(votes_df)

        sitzverteilung = pd.DataFrame(sitzverteilung_per_vote).T.fillna(0).astype(int).sort_index()
        sitzverteilung.index.name = "date"
        sitzverteilung.to_csv(datapath / f"{period}" / "sitzverteilung.csv", sep=";")
        sitzverteilung.reset_index().to_json(self.docs_path / "sitzverteilung.json", orient="records")

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

        # day-level attendance: a member "attended" a day if they cast a real vote on at least
        # one of that day's Abstimmungen, so a day with many bundled votes doesn't outweigh a
        # day with only one when someone was absent
        per_day = self.abstimmung_df.groupby(
            ["Fraktion/Gruppe", "Vorname", "Name", "date"]
        )["nichtabgegeben"].agg(["sum", "size"])
        attended_day = per_day["sum"] < per_day["size"]
        attendance = attended_day.groupby(
            ["Fraktion/Gruppe", "Vorname", "Name"]
        ).agg(days_present="sum", days_total="count").reset_index()
        attendance["days_absent"] = attendance["days_total"] - attendance["days_present"]
        attendance["ratio_days_present"] = attendance["days_present"] / attendance["days_total"]
        attendance["ratio_days_absent"] = attendance["days_absent"] / attendance["days_total"]

        membervotes = membervotes.merge(attendance, on=["Fraktion/Gruppe", "Vorname", "Name"])

        print(membervotes.to_string())
        # save to file
        write_csv_with_comment(membervotes, datapath / f"{period}" / "membervotes.csv", [
            "ja/nein/Enthaltung/ungueltig/nichtabgegeben: votes cast in each category across all Abstimmungen in range",
            "total_votes: sum of the above",
            "ratio_*: category / total_votes (weighted per vote, so a day with many bundled votes counts more)",
            "days_present/days_total/days_absent: sitting days attended/total/missed",
            "  (a day counts as attended if the member cast a real vote on at least one Abstimmung that day)",
            "ratio_days_present/ratio_days_absent: days_present/days_absent divided by days_total (weighted per day, not per vote)",
        ])
        membervotes.round(4).to_json(self.docs_path / "membervotes.json", orient="records")

        # party-level results, weighted by each party's actual daily seat distribution:
        # each vote is attributed to the fraction a member belonged to on that day, so votes
        # are summed exactly as cast, naturally weighted by how many members that fraction
        # actually had present on each day
        partyvotes = self.abstimmung_df.groupby(
            "Fraktion_bei_Abstimmung"
        )[["ja", "nein", "Enthaltung", "ungültig", "nichtabgegeben"]].sum().reset_index()
        partyvotes = partyvotes.rename(columns={"Fraktion_bei_Abstimmung": "Fraktion/Gruppe"})
        partyvotes["total_votes"] = partyvotes["ja"] + partyvotes["nein"] + partyvotes["Enthaltung"] + partyvotes["ungültig"] + partyvotes["nichtabgegeben"]
        partyvotes["ratio_ja"] = partyvotes["ja"] / partyvotes["total_votes"]
        partyvotes["ratio_nein"] = partyvotes["nein"] / partyvotes["total_votes"]
        partyvotes["ratio_Enthaltung"] = partyvotes["Enthaltung"] / partyvotes["total_votes"]
        partyvotes["ratio_ungültig"] = partyvotes["ungültig"] / partyvotes["total_votes"]
        partyvotes["ratio_nichtabgegeben"] = partyvotes["nichtabgegeben"] / partyvotes["total_votes"]
        partyvotes = partyvotes.sort_values("ratio_nichtabgegeben", ascending=True)

        # day-level attendance per party: for each sitting day, what share of that party's
        # members (as of that day) cast a real vote on at least one of the day's Abstimmungen,
        # then average across days so a day with many bundled votes doesn't outweigh a day
        # with only one
        per_member_day = self.abstimmung_df.groupby(
            ["Fraktion_bei_Abstimmung", "date", "Vorname", "Name"]
        )["nichtabgegeben"].agg(["sum", "size"])
        attended_member_day = (per_member_day["sum"] < per_member_day["size"]).rename("attended")

        per_party_day = attended_member_day.groupby(["Fraktion_bei_Abstimmung", "date"]).agg(
            present="sum", size="count"
        )
        per_party_day["ratio_present"] = per_party_day["present"] / per_party_day["size"]

        party_attendance = per_party_day.groupby("Fraktion_bei_Abstimmung").agg(
            days_total=("ratio_present", "size"),
            ratio_days_present=("ratio_present", "mean"),
        ).reset_index()
        party_attendance["ratio_days_absent"] = 1 - party_attendance["ratio_days_present"]
        party_attendance = party_attendance.rename(columns={"Fraktion_bei_Abstimmung": "Fraktion/Gruppe"})

        partyvotes = partyvotes.merge(party_attendance, on="Fraktion/Gruppe")

        print(partyvotes.to_string())
        write_csv_with_comment(partyvotes, datapath / f"{period}" / "partyvotes.csv", [
            "ja/nein/Enthaltung/ungueltig/nichtabgegeben: votes attributed to whichever fraction a member",
            "  belonged to at the time of each vote, not their final/current fraction",
            "total_votes: sum of the above",
            "ratio_*: category / total_votes (weighted per vote, so a day with many bundled votes counts more)",
            "days_total: sitting days this fraction had at least one member recorded",
            "ratio_days_present: for each sitting day, share of that fraction's members who cast a real vote",
            "  that day, averaged equally across days (a bundled-vote day doesn't count extra)",
            "ratio_days_absent: 1 - ratio_days_present",
        ])
        partyvotes.round(4).to_json(self.docs_path / "partyvotes.json", orient="records")

        periods = sorted(p.name for p in self.docs_path.parent.iterdir() if p.is_dir())
        (self.docs_path.parent / "periods.json").write_text(json.dumps(periods))

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
