/*
    Query processing for the search box. Translates operators and parameters
    into a graph search.
*/

var Query = {};   // Namespace

Query.Q = {};     // Prototype

Query.init = function() {
  /* Create a Query object.

     This stores the stack of operations and parameters necessary to perform
     targeted searches in the panda database.
  */ 
  var query = Object.create(Query.Q); 
  query.terms = [];    // Space-deliminited array of query inputs
  query.atoms = {};    // Atoms, which consist of a token and possibly a subject (panda: gin)
                       // TODO: need a tree data structure

  return query;
}


/*
    Operator Definitions and aliases, organized into stages (processing order), and then
    by alphabetical operator order, and then in the alternate languages for searching that
    we're trying to support
*/
Query.ops = {
  "processed" : "___",
  "type": {
    "panda": ['panda', 'red panda', 'パンダ', 'レッサーパンダ'],
    "zoo": ['zoo', '動物園']
  },
  "subtype": {
    "alive": ['alive', 'living'],
    "born": ['born'],
    "dead": ['dead'],
    "died": ['died'],
    "in": ['in']
  },
  "glob": {
    "*": ['*'],
    "?": ['?']
  },
  "boolean": {
    "and": ['and'],
    "or": ['or'],
    "not": ['not'],
    "nor": ['nor']
  },
  "family": {
    "aunt": ['aunt'],
    "brother": ['brother'],
    "cousin": ['cousin'],
    "children": ['children'],
    "dad": ['dad', 'father', 'papa'],
    "grandma": ['grandma', 'grandmother'],
    "grandpa": ['grandpa', 'grandfather'],
    "litter": ['litter'],
    "mate": ['husband', 'mate', 'wife'],
    "mom": ['mom', 'mother'],
    "nephew": ['nephew'],
    "niece": ['niece'],
    "parents": ['parents'],
    "relatives": ['relative', 'relatives'],
    "siblings": ['sibling', 'siblings'],
    "uncle": ['uncle']
  }
}

/*
    Query processing helper and resolution methods
*/
// Is the given input a non-zero id number or not? Helper for other resolve function
Query.isId = function(input) {
  return (isFinite(input) && input != Pandas.def.animal['_id']);
}

// Naive language detection of input strings. TODO: make better :P
// Assume Japanese if any Japanese characters are detected!
Query.myLanguage = function(input) {
  for (var i = 0; i < input.length; i++) {
    if ((str.charCodeAt(i) >= 12352 && str.charCodeAt(i) <= 12543) ||
        (str.charCodeAt(i) >= 19000 && str.charCodeAt(i) <= 44000)) {
      return "jp";
    }
  }
  return "en";
}

// Resolve whether the input is a name or an id, purely based on retrieval attempts.
// Order these attempts as follows:
// 1) Numeric data is treated as an ID, and then searched by its type.
// 2) String data has language detection done
// 3) String exact matched against its type's name, nickname, or othername
// 4) String partial matched against its type's name, nickname, or othername.
//    -- At this point the type either has no results or is null --
// 5) String match as if type was panda
// 6) String match as if type was a zoo
// 7) String match as if type was a location
// 8) String match as if type was a date
Query.resolve = function(single_term, type, language) {
  var bundle = {
    "object": null,
    "language": language,
    "type": type,
  }
  // 1. Process numeric IDs, defaulting to assume it is
  // a panda unless otherwise described.
  if (Query.isId(single_term)) {
    if (type == "zoo") {
      bundle.object = Pandas.searchZooId(single_term);
    } else if (type == "panda") {
      bundle.object = Pandas.searchPandaId(single_term);
    } else {
      bundle.type = "panda";
      bundle.object = Pandas.searchPandaId(single_term);
    }
    return bundle;
  }
  // TODO: the rest of the resolution steps for strings.
  // For now, anything that's not a number is a string.
  // For English strings, our names are capitalized in
  // the database, and strings after a hyphern are also
  // capitalized.
  single_term = single_term.replace(/^\w/, function(chr) {
    return chr.toUpperCase();
  });
  single_term = single_term.replace(/-./, function(chr) {
    return chr.toUpperCase();
  });
  single_term = single_term.replace(/ ./, function(chr) {
    return chr.toUpperCase();
  });
  bundle.object = Pandas.searchPandaName(single_term);
  return bundle;
}

// Given a list of tokens, return a bundle with the current set of 
// tokens processed, and metadata about each found token in the terms.
Query.findTokens = function(terms, tokens) {
  var bundle = {
    "terms": terms
  };
  tokens.forEach(function(token) {
    var index = terms.indexOf(token);
    if (index > -1) {
      bundle[index] = {
      "object": undefined,
       "terms": terms[index],
        "type": "type"
      }
      terms[index] = Query.ops.processed;  // Tombstone a processed token
    }
  });
  return bundle;
}

// Find type operators (panda, zoo) and validate which terms after
// the type might be subjects for those type operators
Query.typeAtoms = function(terms) {
  var bundle = {};
  var types = Query.ops.type.panda.concat(Query.ops.type.zoo);
  types.forEach(function(type_op) {
    var index = terms.indexOf(type_op);
    if (index > -1) {
      bundle[index] = {
      "object": undefined,
       "terms": terms[index],
        "type": "type"
      }
    }
  });
  terms.forEach(function(term) {
    
  });


  return bundle;
}

// Split input into words, and ascribe meanings to each one.
// Return a bundle with an array of terms, with an array of meanings.
Query.tokenize = function(input) {
  var bundle = {};
  var terms = input.split(' ');

  // Pass 1: Find type operators (panda, zoo)

}

/*
    Query processing rules
*/
// TOWRITE MORE

/*
    Hash-Link Processing
*/
// Differentiate between events that change the hashlink on a page.
Query.hashlink = function(input) {
  if ((input.indexOf("#panda_") == 0) || (input.indexOf("#zoo_") == 0)) {
    // in-links don't need a redraw
    return false;
  } else if (input.indexOf("#panda/") == 0) {
    // go-link for a single panda result.
    // for now, just a search result. soon, a detailed result page
    var panda = input.slice(7);
    var bundle = Query.resolve(panda, "panda", "en");
    return bundle.object;
  } else if (input.indexOf("#zoo/") == 0) {
    // go-link for a single zoo result.
    var zoo = input.slice(5);
    var bundle = Query.resolve(zoo, "zoo", "en");
    return bundle.object;
  } else if (input.indexOf("#timeline/") == 0) {
    // show full info and timeline for a panda. TODO
    var panda = input.slice(10);
    var bundle = Query.resolve(panda, "panda", "en");
    return bundle.object;
  } else if (input.indexOf("#query/") == 0) {
    // process a query. TODO: better
    var query = input.slice(7);
    var single_term = query.split(' ')[0];
    var bundle = Query.resolve(single_term, "panda", "en");
    return bundle.object;
  } else {
    // Don't know how to process the hashlink, so do nothing
    return false;
  }
}