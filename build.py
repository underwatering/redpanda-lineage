#!/usr/bin/python3

# This Red Panda Lineage dataset builder takes all source input data and
# creates a JSON file intended for family tree querying.

import configparser
import datetime
import json
import os
import sys

from shared import *

class RedPandaGraph:
    """Class with the redpanda database and format/consistency checks.

    The database is an array of vertices and edges in the graph of red panda
    relationships. A supplemental list of zoos rounds out the red panda data.
    Upon export, these arrays of dicts become a JSON blob.
        
    Vertices represent a panda and their info, while edges represent parent
    and child relationships between animals. In the example below, Karin is
    Harumaki's mom:
      
    { vertices: [{ "_id":1,"en.name":"Harumaki", ...},
                 { "_id":10,"en.name":"Karin", ...}],
      edges: [{"_out":10,"_in":1,"_label":"family"}]}
    """
    def __init__(self):
        self.edges = []
        self.media = []
        self.media_files = []
        self.panda_files = []
        self.photo = {}
        self.photo["credit"] = {}
        self.photo["max"] = 0
        self.summary = {}
        self.summary["birthday"] = 1970
        self.summary["death"] = 1970
        self.vertices = []
        self.wilds = []
        self.wild_files = []
        self.zoos = []
        self.zoo_files = []

    def build_graph(self):
        """Reads in all files to build a red panda graph."""
        self.import_tree(ZOO_PATH, self.import_zoo, self.verify_zoos)
        self.import_tree(WILD_PATH, self.import_wild, self.verify_wilds)
        self.import_tree(PANDA_PATH, self.import_redpanda, self.verify_pandas)
        self.import_tree(MEDIA_PATH, self.import_media, self.verify_media)

    def check_dataset_dates(self):
        """Run checks against the complete tree of red panda dates.

        - Birth date and date of death should not be reversed.
        - Child pandas should not be born before the parent.
        - Child pandas should not be born after the parent died.

        This requires the entire panda dataset to have been read.
        """
        # TODO: graph traverse and date checking
        pass

    def check_dataset_children_ids(self):
        """Check the panda children IDs to ensure they form a family tree.

        - The children IDs should be valid for only one red panda file
        - There should be no loops / I'm my own grandpa situations
        - Each child should have a mother and a father

        This requires the entire children edge dataset to have been read.
        We make stacks of child -> parent -> grandparent ... paths,
        and look for any duplicate IDs in the stacks.
        """
        # Start with the set of pandas that have no children
        childless_ids = [p['_id'] for p in self.vertices
                       if (p['children'] == "none" 
                           or p['children'] == "unknown")]
        # Finish with the pandas that have no recorded parents
        all_child_ids = [x['_out'] for x in self.edges]
        parentless_ids = [y for y in range(1, self.sum_pandas())
                            if y not in all_child_ids]
        # Sets of edges we can start or finish on
        starting_edges = [s for s in self.edges 
                            if s['_out'] in childless_ids]
        finishing_edges = [f for f in self.edges
                             if f['in'] in parentless_ids]
        # This is hard to write :)
        pass

    def check_dataset_litter_ids(self):
        """Check that pandas in the same litter have the same birthday."""
        litter_edges = [a for a in self.edges if a['_label'] == "litter"]
        seen_pairs = []
        for edge in litter_edges:
            if (edge['_in'], edge['_out']) not in seen_pairs:
                try:
                    panda_in = [p for p in self.vertices 
                                  if p['_id'] == edge['_in']][0]
                    panda_out = [p for p in self.vertices 
                                   if p['_id'] == edge['_out']][0]
                except IndexError as e:
                    # One panda in a litter isn't pointing back at the other
                    raise LinkError("""Litter values inconsistent between two pandas,
                                       \nor one panda ID is not in the database: %s""" % edge)
                if self.check_dataset_litter_timeframes(panda_in['birthday'], panda_out['birthday']) == False:
                    raise DateConsistencyError("Pandas in litter don't share birthday: %s, %s"
                                               % (panda_in['en.name'], panda_out['en.name']))
            # Litter relationships are recorded both directions, but we don't need
            # to check the reverse-direction litter relationship
            seen_pairs.append((edge['_in'], edge['_out']))
            seen_pairs.append((edge['_out'], edge['_in']))
        pass

    def check_dataset_litter_timeframes(self, date_one, date_two):
        """Valid litter dates are no more than two days apart."""
        [ year_one, month_one, day_one ] = date_one.split("/")
        [ year_two, month_two, day_two ] = date_two.split("/")
        dt_one = datetime.datetime(int(year_one), int(month_one), int(day_one))
        dt_two = datetime.datetime(int(year_two), int(month_two), int(day_two))
        diff = dt_one - dt_two
        if abs(diff.days) > 2:
            return False
        else:
            return True 

    def check_dataset_duplicate_ids(self, dataset):
        """Check for duplicate IDs in any of the datasets."""
        ids = [a['_id'] for a in dataset]
        # Construct list of duplicates
        dupe_ids = [a for n, a in enumerate(ids) 
                      if a in ids[:n]]
        if len(dupe_ids) > 0:
            # Get list of names for the duplicate pandas
            dupe_names = [a['en.name'] for a in dataset 
                                       if a['_id'] in dupe_ids]
            raise IdError("ERROR: duplicate ids for en.names: %s" 
                          % str(dupe_names)) 

    def check_imported_date(self, date, date_type, sourcepath):
        """
        Dates should all be in the form of YYYY/MM/DD.
        Also, track most recent year that a panda was born or died (datetype).
        """
        try:
            [year, month, day] = date.split("/")
            datetime.datetime(int(year), int(month), int(day))
            if self.summary[date_type] < int(year):
                self.summary[date_type] = int(year)
        except ValueError as e:
            raise DateFormatError("ERROR: %s: invalid YYYY/MM/DD date: %s/%s/%s"
                                  % (sourcepath, year, month, day))

    def check_imported_gender(self, gender, sourcepath):
        """Validate the gender string is correct.

        Allowed strings are one of: 
           m, f, M, F, male, female, オス, or メス

        The gender strings will be cast into just "Male" or "Female", so that
        the website can choose which language to display this data in.
        """
        if gender in ["m", "M", "male", "Male", "オス"]:
            return "Male"
        elif gender in ["f", "F", "female", "Female", "メス"]:
            return "Female"
        else:
            raise GenderFormatError("ERROR: %s: unsupported gender: %s" 
                                    % (sourcepath, gender))

    def check_imported_name(self, name, field, sourcepath):
        """Ensure the name strings are not longer than 80 characters.
    
        This limitation applies to zoos, pandas, and other details, and is
        intended to make text formatting simpler.
        """
        if len(name) > 80:
            raise NameFormatError("ERROR: %s: %s name too long: %s"
                                  % (sourcepath, field, name))
    
    def check_imported_wild_id(self, wild_id, sourcepath):
        """Validate that the ID for a panda's zoo is valid."""
        if wild_id not in [wild['_id'] for wild in self.wilds]:
            raise IdError("ERROR: %s: wild id doesn't exist: %s"
                              % (sourcepath, wild_id))

    def check_imported_panda_wild_path(self, wild_id, sourcepath):
        """Validate that we didn't mis-number a panda's wild id given which directory it sits in."""
        if wild_id not in sourcepath:
            raise IdError("ERROR: %s: file path and wild id don't match: %s"
                              % (sourcepath, wild_id))

    def check_imported_zoo_id(self, zoo_id, sourcepath):
        """Validate that the ID for a panda's zoo is valid."""
        check_id = str(int(zoo_id) * -1)
        if check_id not in [zoo['_id'] for zoo in self.zoos]:
            raise IdError("ERROR: %s: zoo id doesn't exist: %s"
                              % (sourcepath, zoo_id))

    def check_imported_panda_zoo_path(self, zoo_id, sourcepath):
        """Validate that we didn't mis-number a panda's wild id given which directory it sits in."""
        if zoo_id not in sourcepath:
            raise IdError("ERROR: %s: file path and zoo id don't match: %s"
                              % (sourcepath, zoo_id))

    def export_json_graph(self, destpath):
        """Write a JSON representation of the Red Panda graph."""
        export = {}
        export['vertices'] = self.vertices
        export['edges'] = self.edges
        export['_totals'] = {}
        export['_photo'] = {}
        export['_photo']['credit'] = self.photo['credit']
        export['_photo']['entity_max'] = self.photo['max']
        export['_totals']['media'] = len(self.media)
        export['_totals']['wilds'] = len(self.wilds)
        export['_totals']['zoos'] = len(self.zoos)
        export['_totals']['locations'] = len(self.wilds) + len(self.zoos)
        export['_totals']['pandas'] = self.sum_pandas()
        export['_totals']['last_born'] = self.summary['birthday']
        export['_totals']['last_died'] = self.summary['death']
        with open(destpath, 'wb') as wfh:
            wfh.write(json.dumps(export, 
                                 ensure_ascii=False,
                                 indent=4,
                                 sort_keys=True).encode('utf8'))
        print("Dataset exported: %d pandas at %d locations (%d wild, %d zoo)"
              % (export['_totals']['pandas'], export['_totals']['locations'],
                 export['_totals']['wilds'], export['_totals']['zoos']))

    def import_tree(self, path, import_method, verify_method):
        """Given starting path, import all files into the graph.
        
        By adjusting path and import_method, this is used to import either the
        panda data or the zoo data.
        """
        for _, subdir in enumerate(sorted(os.listdir(path))):
            subpath = os.path.join(path, subdir)
            if os.path.isdir(subpath):
                for _, subfile in enumerate(sorted(os.listdir(subpath))):
                    subsubpath = os.path.join(subpath, subfile)
                    if os.path.isfile(subsubpath) and subsubpath.lower().endswith(".txt"):
                        # Import zoos
                        import_method(subsubpath)
                    if os.path.isdir(subsubpath):
                        for _, subsubfile in enumerate(sorted(os.listdir(subsubpath))):
                            datapath = os.path.join(subsubpath, subsubfile)
                            if os.path.isfile(datapath) and datapath.lower().endswith(".txt"):
                                # Import pandas
                                import_method(datapath)
        # Post-import, validate the entire dataset
        verify_method()

    def import_media(self, path):
        """Take a single media file and convert it into a Python dict.

        Media files are expected to have a header of [media]. Any fields defined
        under that header will be consumed into a list of photos or videos. All
        of these media files should have two or more pandas in them.
        """
        media_vertex = {}
        infile = configparser.ConfigParser()
        infile.read(path, encoding='utf-8')
        # Use the path name for error messages or assignments
        for field in infile.items("media"):
            if (field[0].find("photo") != -1 and
                len(field[0].split(".")) == 2):
                    # Process a small set of photo credits for all the pandas
                    # author = infile.get("media", field[0] + ".author")
                    # if author in self.photo["credit"].keys():
                    #     self.photo["credit"][author] = self.photo["credit"][author] + 1
                    # else:
                    #     self.photo["credit"][author] = 1
                    # Track what the max number of panda photos an object has is
                    # test_count = int(field[0].split(".")[1])
                    # if test_count > self.photo["max"]:
                    #    self.photo["max"] = test_count
                    # Accept the data and continue
                    media_vertex[field[0]] = field[1]
            # TODO: track video info for apple counting as well
            else:
                # Accept the data and move along
                media_vertex[field[0]] = field[1]
        self.media.append(media_vertex)
        self.vertices.append(media_vertex)
        self.media_files.append(path)

    def import_redpanda(self, path):
        """Take a single red panda file and convert it into a Python dict.

        Panda files are expected to have a header of [panda]. Any fields defined
        under that header will be consumed into the pandas datastore. 
        
        Fields with specific formats, like dates or names or ids, get validated
        upon importing. This includes making sure birthplace and zoo refer to 
        valid zoos. Relationship fields or panda ID checks are deferred until
        the entire set of panda data is imported.

        Since pandas live at zoos and we need to check zoo references, the list
        of zoos must be imported prior to any red pandas being imported. 
        """
        panda_edges = []
        panda_vertex = {}
        infile = configparser.ConfigParser()
        infile.read(path, encoding='utf-8')
        panda_name = infile.get("panda", "en.name")   # For error messages
        panda_id = infile.get("panda", "_id")         # or assignments
        for field in infile.items("panda"):
            if (field[0].find("death") != -1 or
                field[0].find("birthday") != -1):
                # Record that an animal has died or was born, 
                # regardless if the date has been recorded or not.
                if field[1] != "unknown":
                    self.check_imported_date(field[1], field[0], path)
                panda_vertex[field[0]] = field[1]
            if field[1] == "unknown" or field[1] == "none":
                # Basic null checks. Don't add this to the vertex
                continue
            elif field[0].find("name") != -1:
                # Name rule checking
                self.check_imported_name(field[1], field[0], path)
                panda_vertex[field[0]] = field[1]
            elif field[0].find("gender") != -1:
                # Gender rules
                gender = self.check_imported_gender(field[1], path)
                panda_vertex[field[0]] = gender
            elif (field[0].find("birthplace") != -1):
                if (field[1].find("wild.") != -1):
                  # Wild ID rules
                  wild_id = field[1]
                  self.check_imported_wild_id(field[1], path)
                  # Add a wild edge to the list that's a wild location
                  wild_edge = {}
                  wild_edge['_out'] = panda_id
                  wild_edge['_in'] = wild_id
                  wild_edge['_label'] = field[0]
                  panda_edges.append(wild_edge)
                else:
                  # Zoo ID rules
                  # To differentiate Zoo IDs from pandas, use negative IDs
                  zoo_id = str(int(field[1]) * -1)
                  self.check_imported_zoo_id(field[1], path)
                  # Add a birthplace or zoo edge to the list that's a zoo
                  zoo_edge = {}
                  zoo_edge['_out'] = panda_id
                  zoo_edge['_in'] = zoo_id
                  zoo_edge['_label'] = field[0]
                  panda_edges.append(zoo_edge)
            elif field[0].find("children") != -1:   
                # Process children IDs
                children = field[1].replace(" ","").split(",")
                for child_id in children:
                    panda_edge = {}
                    panda_edge['_out'] = panda_id
                    panda_edge['_in'] = child_id
                    panda_edge['_label'] = "family"
                    panda_edges.append(panda_edge)
            elif field[0].find("litter") != -1:   
                # Process whether pandas were in the same litter or not
                litter = field[1].replace(" ","").split(",")
                for sibling_id in litter:
                    panda_edge = {}
                    panda_edge['_out'] = panda_id
                    panda_edge['_in'] = sibling_id
                    panda_edge['_label'] = "litter"
                    panda_edges.append(panda_edge)
            elif (field[0].find("photo") != -1 and
                  len(field[0].split(".")) == 2):
                # Process a small set of photo credits for all the pandas
                author = infile.get("panda", field[0] + ".author")
                if author in self.photo["credit"].keys():
                    self.photo["credit"][author] = self.photo["credit"][author] + 1
                else:
                    self.photo["credit"][author] = 1
                # Track what the max number of panda photos an object has is
                test_count = int(field[0].split(".")[1])
                if test_count > self.photo["max"]:
                    self.photo["max"] = test_count
                # Accept the data and continue
                panda_vertex[field[0]] = field[1]
            elif (field[0].find("wild") != -1):
                # Wild ID rules
                wild_id = field[1]
                self.check_imported_wild_id(field[1], path)
                self.check_imported_panda_wild_path(field[1], path)
                # Add a wild edge to the list that's a wild location
                wild_edge = {}
                wild_edge['_out'] = panda_id
                wild_edge['_in'] = wild_id
                wild_edge['_label'] = field[0]
                panda_edges.append(wild_edge)
            elif (field[0].find("zoo") != -1):
                # Zoo ID rules
                # To differentiate Zoo IDs from pandas, use negative IDs
                zoo_id = str(int(field[1]) * -1)
                self.check_imported_zoo_id(field[1], path)
                self.check_imported_panda_zoo_path(field[1], path)
                # Add a birthplace or zoo edge to the list that's a zoo
                zoo_edge = {}
                zoo_edge['_out'] = panda_id
                zoo_edge['_in'] = zoo_id
                zoo_edge['_label'] = field[0]
                panda_edges.append(zoo_edge)
            else:
                # Accept the data and move along
                panda_vertex[field[0]] = field[1]
        self.edges.extend(panda_edges)
        self.vertices.append(panda_vertex)
        self.panda_files.append(path)

    def import_wild(self, path):
        """Take a single wild location file and convert it into a Python dict.
        
        Wild files are expected to have a header of [wild]. Any fields defined
        under that header will be consumed into the wild datastore. Every panda
        must have a link to a zoo or a wild location.
        """
        wild_entry = {}
        infile = configparser.ConfigParser()
        infile.read(path, encoding='utf-8')
        for field in infile.items("wild"):
            # Use negative numbers for zoo IDs, to distinguish from pandas
            [ key, value ] = [field[0], field[1]]
            if (key.find("photo") != -1 and
                len(key.split(".")) == 2):
                author = infile.get("wild", key + ".author")
                if author in self.photo["credit"].keys():
                    self.photo["credit"][author] = self.photo["credit"][author] + 1
                else:
                    self.photo["credit"][author] = 1
            wild_entry[key] = value
        self.wilds.append(wild_entry)
        self.wild_files.append(path)
        self.vertices.append(wild_entry)
        
    def import_zoo(self, path):
        """Take a single zoo file and convert it into a Python dict.
        
        Zoo files are expected to have a header of [zoo]. Any fields defined
        under that header will be consumed into the zoo datastore. Every panda
        must have a link to a zoo or a wild location.
        """
        zoo_entry = {}
        infile = configparser.ConfigParser()
        infile.read(path, encoding='utf-8')
        for field in infile.items("zoo"):
            # Use negative numbers for zoo IDs, to distinguish from pandas
            [ key, value ] = [field[0], field[1]]
            if key == '_id':
                value = str(int(field[1]) * -1)
            elif (key.find("photo") != -1 and
                  len(key.split(".")) == 2):
                author = infile.get("zoo", key + ".author")
                if author in self.photo["credit"].keys():
                    self.photo["credit"][author] = self.photo["credit"][author] + 1
                else:
                    self.photo["credit"][author] = 1
            zoo_entry[key] = value
        self.zoos.append(zoo_entry)
        self.zoo_files.append(path)
        self.vertices.append(zoo_entry)

    def find_matching_edges(self, outp, inp, label):
        """Find matching edges in either direction.

        Ex: If _in=8 and _out=2, match either that edge or _in=2 and _out=8
        """
        return [a for a in self.edges
                if ((a['_label'] == label) and
                    ((a['_out'] == outp and a['_in'] == inp) or  
                     (a['_in'] == outp and a['_out'] == inp)))]

    def sum_pandas(self):
        """Panda count is just the count of the number of panda files imported."""
        return len(self.panda_files)

    def verify_media(self):
        """All checks to ensure that the group media vertices are good."""
        self.check_dataset_duplicate_ids(self.media)

    def verify_pandas(self):
        """All checks to ensure that the panda dataset is good."""
        self.check_dataset_duplicate_ids(self.vertices)
        # self.check_dataset_children_ids()
        self.check_dataset_litter_ids()
        self.check_dataset_dates()

    def verify_wilds(self):
        """All checks to ensure that the zoo dataset is good."""
        self.check_dataset_duplicate_ids(self.wilds)

    def verify_zoos(self):
        """All checks to ensure that the zoo dataset is good."""
        self.check_dataset_duplicate_ids(self.zoos)


def vitamin():
    """
    Based on a completed Red Panda database, and on the contents of all Javascript and
    HTML sources here, build a unique set of characters for display in the lineage
    interface. This character set is necessary to instruct TypeSquare on which characters
    we want to download in our font.
    """
    vitamin = "&amp;&copy;&lsquo;&rsquo;&ldquo;&rdquo;&nacute;"  # &-encoded HTML characters to start
    lists = []
    manifest = [
        "export/redpanda.json",
        "index.html",
        "js/pandas.js",
        "js/show.js",
        "fragments/en/about.html",
        "fragments/jp/about.html",
        "fragments/en/links.html",
        "fragments/jp/links.html"
    ]
    for fn in manifest:
        with open(fn, 'r') as rfh:
            raw = rfh.read()
            lists += list(set(raw))  # Uniquify values
    lists = list(set(lists))   # Uniquify lists of values
    lists.sort()
    vitamin += ''.join(lists).replace("\n", "")
    page = ""
    with open("index.html", mode='r', encoding='utf-8') as rfh:
        page = rfh.read()
        page = page.replace('${vitamins}', vitamin)
    with open("index.html", mode='w', encoding="utf-8") as wfh:
        wfh.write(page)

if __name__ == '__main__':
    """Initialize all library settings, build, and export the database."""
    p = RedPandaGraph()
    p.build_graph()
    p.export_json_graph(OUTPUT_PATH)
    # Only do this in CI when publishing a real page
    if len(sys.argv) > 1:
        if sys.argv[1] == "--publish":
            vitamin()
