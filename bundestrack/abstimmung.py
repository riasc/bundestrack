import json
import re
import unicodedata
import utility
from pathlib import Path
import pandas as pd

def write_csv_with_comment(df, path, comment_lines):
    with open(path, "w", newline="") as f:
        for line in comment_lines:
            f.write(f"# {line}\n")
        df.to_csv(f, index=False, sep=";")

def fold_ascii(s):
    s = s.replace("ß", "ss").replace("ẞ", "SS")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()

def slugify(vorname, name):
    # plain lowercase ASCII: avoids relying on git/filesystem Unicode normalization
    # (macOS stores accented filenames decomposed, which can byte-mismatch a composed
    # slug elsewhere) and keeps URLs simple
    s = re.sub(r"\s+", "-", f"{vorname}-{name}".strip())
    s = fold_ascii(s).lower()
    return re.sub(r"[^\w\-]", "", s)

def normalize_key(s):
    # accent/case-insensitive, so e.g. "Ahmetovic" and "Ahmetović" across different
    # periods' source files resolve to the same person instead of two separate entries
    return fold_ascii(s).lower()


class NamentlicheAbstimmung:
    def __init__(self, datapath, period, start, end, docs_path=Path("docs/data")):
        files = utility.list_files(datapath / f"{period}" / "abstimmungen")
        range_files = utility.subset_files(files, start, end)
        self.period = str(period)
        self.docs_path = docs_path / f"{period}"
        self.docs_path.mkdir(parents=True, exist_ok=True)
        # members are shared across periods (someone can be re-elected), so their detail
        # file/slug lives outside any single period's folder and gets merged across runs
        self.members_dir = docs_path / "members"
        self.members_dir.mkdir(parents=True, exist_ok=True)
        self.slug_registry_path = self.members_dir / "_slugs.json"
        self.slug_registry = json.loads(self.slug_registry_path.read_text()) if self.slug_registry_path.exists() else {}

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
        choice_cols = ["ja", "nein", "Enthaltung", "ungültig", "nichtabgegeben"]
        self.abstimmung_df["choice"] = self.abstimmung_df[choice_cols].idxmax(axis=1)
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

        # slug per member, shared across periods (someone can be re-elected) so their
        # detail page/data stays a single entry regardless of which period links to it
        membervotes["slug"] = membervotes.apply(
            lambda row: self.get_or_create_slug(row["Vorname"], row["Name"]), axis=1
        )

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

        # per-member detail: full vote history (date, fraction at the time, choice) plus
        # any fraction changes, fetched lazily by the member detail page. Stored one file
        # per person (not per period) and merged so a member re-elected across periods
        # keeps a single entry, with a section per period they served
        slug_by_member = {(row["Vorname"], row["Name"]): row["slug"] for _, row in membervotes.iterrows()}

        for (vorname, name), group in self.abstimmung_df.groupby(["Vorname", "Name"]):
            votes = group.sort_values("date")[["date", "Fraktion_bei_Abstimmung", "choice"]] \
                .rename(columns={"Fraktion_bei_Abstimmung": "fraktion"}).to_dict("records")

            fraction_changes = []
            previous_fraktion = None
            for vote in votes:
                if previous_fraktion is not None and vote["fraktion"] != previous_fraktion:
                    fraction_changes.append({"date": vote["date"], "from": previous_fraktion, "to": vote["fraktion"]})
                previous_fraktion = vote["fraktion"]

            slug = slug_by_member[(vorname, name)]
            detail_path = self.members_dir / f"{slug}.json"
            detail = json.loads(detail_path.read_text()) if detail_path.exists() else {
                "Vorname": vorname, "Name": name, "periods": {}
            }
            detail["periods"][self.period] = {
                "Fraktion/Gruppe": self.members[(vorname, name)],
                "votes": votes,
                "fraction_changes": fraction_changes,
            }
            detail_path.write_text(json.dumps(detail, ensure_ascii=False))

        self.slug_registry_path.write_text(json.dumps(self.slug_registry, ensure_ascii=False))

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

        periods = sorted(
            (p.name for p in self.docs_path.parent.iterdir() if p.is_dir() and p.name.isdigit()),
            key=int,
        )
        (self.docs_path.parent / "periods.json").write_text(json.dumps(periods))

    def get_or_create_slug(self, vorname, name):
        key = f"{normalize_key(vorname)}|{normalize_key(name)}"
        if key not in self.slug_registry:
            base = slugify(vorname, name)
            existing = set(self.slug_registry.values())
            slug, n = base, 2
            while slug in existing:
                slug = f"{base}-{n}"
                n += 1
            self.slug_registry[key] = slug
        return self.slug_registry[key]

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
