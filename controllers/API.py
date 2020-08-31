# -*- coding: utf-8 -*-
import sys
import re
import json
from random import random
from OZfunctions import punctuation_to_space, __check_version, is_logographic, child_leaf_query
from OZfunctions import ids_from_otts_string, nodes_info_from_string
"""
This contains the API functions - node_details, image_details, search_names, and search_sponsors. search_node also exists, which is a combination of search_names and search_sponsors.
# request.vars:
# -- node_ids: '1,2,3'
# -- leaf_ids: '2,3,4'
# -- image_source: 'best_any' or 'best_verified' or 'best_pd'
# -- question: should this contain the 'linkouts' functions, which are also a sort of API.

We should probably compile all docstrings in these files into markdown documentation
"""


def version():
    v = __check_version()
    try:
        return dict(version=int(v))
    except ValueError:
        return dict(version=None, error=v)


def format_leaf(leaf):
    return dict(
        name=leaf[22],
        id=leaf[0],
        ott=leaf[5],
        url=thumbnail_url(leaf[31], leaf[32])
    )


def format_node(node):
    return dict(
        name=node[6],
        id=node[0],
        age=node[7],
        ott=node[8],
        wikidata=node[8],
        eol=node[10]
    )


def get_quiz_species():
    try:
        """
        TODO
        - use db abstraction layer instead of raw queries
        - ensure that branching_nodes_response returns two nodes that have the necessary number of valid leaves
        - allow user to pass in the parent node ID, right now it is hardcoded to chordata
        - pass language to endpoint
        - disallow duplicate leaves
        - make algorithm "smarter"
        - feed popularity into orderby function
        """
        response.headers["Access-Control-Allow-Origin"] = '*'

        parent_ott = request.vars.parent_ott

        parent_node_response = db.executesql(
            '''
            select id, node_rgt from ordered_nodes where ott = {parent_ott}
            '''.format(parent_ott=parent_ott)
        )

        node_response = db.executesql(
            '''
            select id, parent, real_parent, node_rgt, leaf_lft, leaf_rgt, name, age, ott, popularity,
            (select count(*) from ordered_nodes d where d.real_parent = a.id and d.leaf_rgt - d.leaf_lft > 10) as num_valid_children
            from ordered_nodes a
            where id between {left_node_id} and {right_node_id} and popularity > 0
            having num_valid_children > 1
            order by power(popularity, 0.1) * rand() desc
            limit 1
            '''.format(left_node_id=parent_node_response[0][0], right_node_id=parent_node_response[0][1])
        )
        parent_node = node_response[0]

        branching_nodes_response = db.executesql(
            '''
            select distinct * from ordered_nodes
            where real_parent = {parent_node_id}
            order by rand()
            limit 2
            '''.format(parent_node_id=parent_node[0])
        )

        node_left = branching_nodes_response[0]
        node_right = branching_nodes_response[1]

        print(dict(parent_node_id=parent_node[0]))

        # todo: can be duplicates here
        left_leaves_response = db.executesql(
            '''
            (select *, (select age from ordered_nodes nodes where leaves.real_parent = id) as parent_age
            from ordered_leaves leaves
            join vernacular_by_ott on (leaves.ott = vernacular_by_ott.ott and vernacular_by_ott.lang_primary = 'en' and vernacular_by_ott.preferred = 1)
            join images_by_ott on leaves.ott = images_by_ott.ott and best_any = 1 and images_by_ott.rating > 25000
            where leaves.id between {leaf_left} and {leaf_right}
            group by leaves.ott
            order by power(parent_age + 1, 0.8) * rand() desc
            limit 1)
            union all
            (select *, (select age from ordered_nodes nodes where leaves.real_parent = id) as parent_age
            from ordered_leaves leaves
            join vernacular_by_ott on (leaves.ott = vernacular_by_ott.ott and vernacular_by_ott.lang_primary = 'en' and vernacular_by_ott.preferred = 1)
            join images_by_ott on leaves.ott = images_by_ott.ott and best_any = 1 and images_by_ott.rating > 25000
            where leaves.id between {leaf_left} and {leaf_right}
            group by leaves.ott
            order by power(parent_age + 1, 0.8) * rand() asc
            limit 1)
            '''.format(leaf_left=node_left[4], leaf_right=node_left[5])
        )

        right_leaves_response = db.executesql(
            '''
            select *, (select age from ordered_nodes nodes where leaves.real_parent = id) as parent_age
            from ordered_leaves leaves
            join vernacular_by_ott on (leaves.ott = vernacular_by_ott.ott and vernacular_by_ott.lang_primary = 'en' and vernacular_by_ott.preferred = 1)
            join images_by_ott on leaves.ott = images_by_ott.ott and best_any = 1 and images_by_ott.rating > 25000
            where leaves.id between {leaf_left} and {leaf_right}
            group by leaves.ott
            order by power((parent_age + 1) * (popularity / 100), 0.05) * rand() desc
            limit 1
            '''.format(leaf_left=node_right[4], leaf_right=node_right[5])
        )

        rand = random()
        leaf_1 = left_leaves_response[1] if rand > 0.5 else right_leaves_response[0]
        leaf_2 = left_leaves_response[1] if rand <= 0.5 else right_leaves_response[0]

        return dict(
            leaf_compare=format_leaf(left_leaves_response[0]),
            leaf_1=format_leaf(leaf_1),
            leaf_2=format_leaf(leaf_2),
        )
    except Exception as e:
        print(str(e))
        raise HTTP(500)


def nearest_common_ancestor():
    response.headers["Access-Control-Allow-Origin"] = '*'

    try:
        leaves = json.loads(request.vars.leaves)

        node = db((db.ordered_nodes.leaf_lft <=
                   leaves[0]) & (db.ordered_nodes.leaf_rgt >=
                                 leaves[0]) & (db.ordered_nodes.leaf_lft <=
                                               leaves[1]) & (db.ordered_nodes.leaf_rgt >=
                                                             leaves[1])).select(db.ordered_nodes.ALL, orderby=~db.ordered_nodes.id, limitby=(0, 1)).first()

        if node is None:
            return None

        return dict(
            id=node.id,
            ott=node.ott,
            eol=node.eol,
            wikidata=node.wikidata,
            age=node.age,
            name=node.name
        )
    except Exception as e:
        print(str(e))
        raise HTTP(500)


def node_details():
    """
    This is the main API call, and should be optimized to within an inch of its life. Some ideas:
    1) Move it to another process (not web2py). E.g. Falcon. See http://klen.github.io/py-frameworks-bench/
    2) Put some of the load on the SQL server, but adding SQL joins rather than making 7
        queries (but mysql does not support full outer joins, which we would need)
    3) Do not return info about the leaf taxa in the representative image array, as we
        probably end up returning these many times over and over again. Instead, we could
        return the leaf IDs, and get the client to work out if we need to add them to the
        next API call.
    """
    session.forget(response)
    response.headers["Access-Control-Allow-Origin"] = '*'
    try:
        language = request.vars.lang or request.env.http_accept_language or 'en'
        return nodes_info_from_string(
            request.vars.leaf_ids or "",
            request.vars.node_ids or "",
            include_names_in=language,
            image_type=request.vars.get('image_source') or "")
    except:  # E.g. if bad data has been passed in
        return {}


def image_details():
    """
    e.g. image_details.json?2=25677433,27724652&1=31925837,1
    where 1 and 2 are values from src_flags
    """
    session.forget(response)
    response.headers["Access-Control-Allow-Origin"] = '*'
    try:
        all_cols = ['rights', 'licence']
        col_names = {nm: index for index, nm in enumerate(all_cols)}
        queries = []
        image_details = {}
        for v in request.vars:
            if v.isdigit() and int(v) in inv_src_flags:
                ids = request.vars[v]
                if re.search("[^-\d,]", ids):
                    raise  # list of ids must only consist of digits and commas, otherwise this is a malicious API call
                if re.search("^,|[-,]$|,,|-[-,]|\d-", ids):
                    raise  # ban commas at start, and before other commas, ban minus signs and commas at end,
                # if we get here, ids should only contain numbers (negative or positive) with commas between
                image_details[int(v)] = {int(
                    id): None for id in ids.split(",")}
                q = "(SELECT " + ",".join(['src', 'src_id'] + all_cols) + \
                    " FROM {} WHERE src = {} AND src_id IN({}))"
                queries.append(q.format('images_by_ott', v, ids))
                queries.append(q.format('images_by_name', v, ids))
        for row in db.executesql(" UNION ALL ".join(queries)):
            image_details[row[0]][row[1]] = row[2:]
        return {'headers': col_names, 'image_details': image_details}
    except:  # e.g. if bad data has been passed in
        return {'errors': ['Bad data passed in']}

# Search


def search_node():
    """
    searches both taxon name (latin & vernacular) and sponsor text, but only looks for sponsors when the number of taxa returned is low
    So that we don't pollute the taxon searches with lots of sponsorship stuff
    """
    session.forget(response)
    response.headers["Access-Control-Allow-Origin"] = '*'
    searchFor = make_unicode(request.vars.query or '')
    try:
        if myconf.take('general.log_search_strings'):
            if request.vars.no_log:
                # 'no_log' flag set: this is probably us blatting the search for testing purposes
                pass
            else:
                db.search_log.update_or_insert(
                    db.search_log.search_string == searchFor, search_string=searchFor, search_count=db.search_log.search_count+1)

    except:
        pass
    res1 = search_for_name()
    if len(res1['leaf_hits']) + len(res1['node_hits']) < 15:
        res2 = search_sponsor(searchFor, "all", res1.get('lang'))
    else:
        res2 = {"reservations": {}, "nodes": {}, "leaves": {}}
    return {"nodes": res1, "sponsors": res2}


def search_init():
    """
    This is called at the very start of loading a tree view page. It looks in
    request.vars to return the OneZoom id of taxa corresponding to:
    -- Number: ott 
    -- String: name
    return a list of leaf (negative) or node ids given ott number or scientific name

    The ott number is given priority. If this matches a single leaf, this is the only id
    returned. If it matches a single node, this is the only one returned.

    If multiple leaves/nodes match, and names are given, it tries to find a leaf or node
    matching both name and ott. If none match both, it just returns all possible hits
    (or an empty error if no hits at all).
    """
    session.forget(response)
    ids = set()
    try:
        ott = int(request.vars.get('ott'))
        query = db.ordered_leaves.ott == ott
        ids.update([-r.id for r in db(query).select(db.ordered_leaves.id)])
        # Always return the leaf if there is a single hit
        if len(ids) == 1:
            return {"ids": list(ids)}

        query = db.ordered_nodes.ott == ott
        ids.update([r.id for r in db(query).select(db.ordered_nodes.id)])
        # If a single node, don't worry about the name
        if len(ids) == 1:
            return {"ids": list(ids)}
    except (TypeError, ValueError) as error:
        pass  # Some problem converting ott to int, try on name
    try:
        tidy_latin = request.vars.name.replace("_", " ")
        query = db.ordered_leaves.name == tidy_latin
        name_ids = set([r.id for r in db(query).select(db.ordered_leaves.id)])
        query = db.ordered_nodes.name == request.vars.name
        name_ids.update([r.id for r in db(query).select(db.ordered_nodes.id)])

        # If we already had some ids, use names to refine
        if len(ids & name_ids):
            ids &= name_ids
        elif len(ids | name_ids):
            ids |= name_ids
    except:
        pass  # could be a problem with getting a name
    if ids:
        return {"ids": sorted(ids)}
    return {"empty": request.vars.ott}


def search_for_sciname():
    """
    Search for a starting match on the latin name as stored in the ordered_leaves or ordered_nodes tables
    String passed in is ?query=xxxx
    """
    session.forget(response)
    response.headers["Access-Control-Allow-Origin"] = '*'
    try:
        searchFor = " ".join(make_unicode(request.vars.query or "").split())
        result = []
        if searchFor and len(searchFor) > 1:
            if not request.vars.nodes_only:
                result += [[r.id, r.ott, r.name] for r in
                           db(db.ordered_leaves.name.startswith(searchFor)).select(db.ordered_leaves.id, db.ordered_leaves.ott, db.ordered_leaves.name)]
            if not request.vars.leaves_only:
                result += [[r.id, r.ott, r.name] for r in
                           db(db.ordered_nodes.name.startswith(searchFor)).select(db.ordered_nodes.id, db.ordered_nodes.ott, db.ordered_nodes.name)]
        return dict(result=result)
    except:
        if is_testing:
            raise
        else:
            return {}

# request.vars contains:
#  -- String: query
#  -- String: 'lang' (default 'en') - used to override the default of request.env.http_accept_language
#  -- Boolean: 'sorted' (default False)
#  -- Number: 'limit'
#  -- Number: 'page' (default 0)
#  -- Boolean: 'include_price' (default False)
#  -- String: 'restrict_tables is one of 'leaves', 'nodes' or None.(default None)
#  Sanitize parameters and then do actually search.


def search_for_name():
    session.forget(response)
    response.headers["Access-Control-Allow-Origin"] = '*'
    language = request.vars.lang or request.env.http_accept_language or 'en'
    try:
        searchFor = make_unicode(request.vars.query or "")
        first_lang = language.split(',')[0]
        lang_primary = first_lang.split("-")[0]
        order = True if (request.vars.get('sorted')) else False
        limit = request.vars.get('limit')
        start = request.vars.get('start') or 0
        include_price = True if (request.vars.get('include_price')) else False
        restrict_tables = request.vars.get('restrict_tables')
        return search_by_name(searchFor, language, order_by_popularity=order, limit=limit, start=start, restrict_tables=restrict_tables, include_price=include_price)
    except:
        if is_testing:
            raise
        else:
            return {'lang': language}


def search_by_name(searchFor, language, order_by_popularity=False, limit=None, start=0, restrict_tables=None, include_price=False):
    """
    Search in latin and vernacular names for species. To look only in leaves, set restrict_tables to 'leaves'.
    To look only in nodes set it to 'nodes', otherwise we default to searching in both


    We can do fast matches with against the start of words using full test searches in boolean mode, e.g. 
        match(vernacular) against('o*' in boolean mode) and lang_primary='en'
    (note that although you can put an asterisk at the start of the match it is ignored by mysql)

    The problem is that the minimum word size is set to innodb_ft_min_token_size = 3, so that one and two-letter
    words are excluded from the index, and since we share databases with other users, we can't change this.
    We can still match *search terms* of one and two letters, e.g. 'ox*' will match some things (e.g. 'oxford')
    but nothing of 2 letters (e.g. 'ox').

    So if we want to also match against one or two letter words, we need to use normal text matches
    *in addition* to full text matches. For speed, we are restricted to matching at the start of the 
    entire phrase
    """

    """
    1) Kill off any searches where all non-chinese words are <= 1 letter
    1. if string length < 3, then it would run a start match. For example, search for 'zz' would return 'zz plant', search for 'ox ox' would
    return 'ox oxon'(if it exists)
    2. all words' length >= 3, then it would run natural language search on each word.
    3. parts of the words' length >= 3, then it would do a natural language search on these words and then do a containing search on the rest words.
    4. TO DO: substitute all punctuation with spaces (except apostrophe, dash, dot & 'times'
    5. TO DO: in English, we should remove apostrophe-s at the end of a word
    """
    lang_primary = language.split(',')[0].split("-")[0].lower()
    base_colnames = ['id', 'ott', 'name', 'popularity']
    if include_price:
        base_colnames += ['price']
    colnames = base_colnames + ['vernacular', 'extra_vernaculars']
    colname_map = {nm: index for index, nm in enumerate(colnames)}

    try:
        originalSearchFor = searchFor
        searchFor = punctuation_to_space(searchFor).split()
        if len(searchFor) == 0 or all([(len(word) <= 1 and not is_logographic(word, lang_primary)) for word in searchFor]):
            raise
        longWords = []
        shortWords = []
        for word in searchFor:
            if len(word) >= 3:
                longWords.append(word)
            else:
                shortWords.append(word)

        searchForCommon = " ".join(["+*" + word + "*" for word in longWords])
        searchForLatin = searchForCommon

        # Double percentage sign to escape %.
        searchForShortContains = " ".join(
            ["and {0} like '%%" + word + "%%'" for word in shortWords])
        names = set()
        otts = set()

        # query the matches against latin and vernaculars in one go, and
        # http://stackoverflow.com/questions/7082522/using-sql-join-and-union-together
        if restrict_tables == "leaves":
            results = {'ordered_leaves': []}
        elif restrict_tables == "nodes":
            results = {'ordered_nodes': []}
        else:
            results = {'ordered_leaves': [], 'ordered_nodes': []}

        for tab in results:
            initial_cols = ",".join(base_colnames)
            if tab == "ordered_nodes":
                initial_cols = initial_cols.replace(
                    "price", "NULL AS price")  # nodes don't have a price
            query = 'select ' + initial_cols + ' from ' + tab + ' {0}'
            query += ' union select ' + initial_cols + ' from ' + tab + \
                ' where ott in (select distinct ott from vernacular_by_ott {1})'
            query += ' union select ' + initial_cols + ' from ' + tab + \
                ' where name in (select distinct name from vernacular_by_name {2})'

            if len(longWords) > 0:
                query = query.format(
                    'where match(name) against({0} in boolean mode) ' +
                    searchForShortContains.format('name'),
                    'where match(vernacular) against({0} in boolean mode) and lang_primary={0} ' +
                    searchForShortContains.format('vernacular'),
                    'where match(vernacular) against({0} in boolean mode) and lang_primary={0} ' +
                    searchForShortContains.format('vernacular')
                )
            else:
                query = query.format(
                    "where name like {0}",
                    "where lang_primary={0} and vernacular like {0}",
                    "where lang_primary={0} and vernacular like {0}"
                )
            if order_by_popularity:
                query += ' ORDER BY popularity DESC'
            if limit:
                query += ' LIMIT ' + str(int(limit))
                if start:
                    query += ' OFFSET ' + str(int(start))

            if len(longWords) > 0:
                results[tab] = [list(row) for row in db.executesql(query.format(
                    db.placeholder), (searchForLatin, searchForCommon, lang_primary, searchForCommon, lang_primary))]
            else:
                temp = originalSearchFor + "%%"
                results[tab] = [list(row) for row in db.executesql(query.format(
                    db.placeholder), (temp, lang_primary, temp, lang_primary, temp))]
            # search for common name
            for row in results[tab]:
                if row[1]:
                    otts.add(row[1])
                elif row[2]:
                    names.add(row[2])
        # now find the vernacular names for these, so we can  save them in 'vernaculars' and 'extra_vernaculars'
        ott_to_vern = {}
        name_to_vern = {}
        if len(otts):
            # save the match status in the query return, so we can use it later.
            if len(longWords) > 0:
                mtch = 'if(match(vernacular) against({} in boolean mode), TRUE, FALSE) as mtch'
                query = ("select ott,vernacular,preferred,mtch from (select ott, vernacular, preferred, src, " + mtch +
                         " from vernacular_by_ott where lang_primary={} and ott in ({})) t where (mtch or preferred) order by preferred DESC,src").format(db.placeholder, db.placeholder, ",".join([db.placeholder]*len(otts)))
                temp = db.executesql(
                    query, [searchForCommon] + [lang_primary] + list(otts))
            else:
                mtch = "if(vernacular like {}, TRUE, FALSE) as mtch"
                query = ("select ott,vernacular,preferred,mtch from (select ott, vernacular, preferred, src, " + mtch +
                         " from vernacular_by_ott where lang_primary={} and ott in ({})) t where mtch order by preferred DESC,src")
                query = query.format(db.placeholder, db.placeholder, ",".join(
                    [db.placeholder]*len(otts)))
                temp = db.executesql(
                    query, [originalSearchFor+'%%'] + [lang_primary] + list(otts))

            for row in temp:
                if row[0] not in ott_to_vern:  # nothing saved yet
                    if row[2]:  # this is a preferred match, and is the first preferred encountered, so is the standard vernacular
                        if row[3]:  # this is a match, so we don't need to store any non-preferred versions
                            ott_to_vern[row[0]] = [row[1]]
                        else:  # save space for non-preferred matches: there must be at least one, unless the match was via sciname
                            ott_to_vern[row[0]] = [row[1], []]
                    else:  # this is not preferred: no standard vernacular, save as an extra
                        ott_to_vern[row[0]] = [None, [row[1]]]
                else:
                    # the entry exists, so we must have already filled out some vernaculars
                    # another match, and standard vernacular didn't match: add to extras
                    if row[3] and len(ott_to_vern[row[0]]) == 2:
                        ott_to_vern[row[0]][1].append(row[1])
        if len(names):
            # same again, but match on name
            query = "select name,vernacular,preferred,mtch from (select name, vernacular, preferred, src, if(match(vernacular) against({} in boolean mode), TRUE, FALSE) as mtch from vernacular_by_name where lang_primary={} and name in ({})) t where (mtch or preferred) order by preferred DESC,src".format(
                db.placeholder, db.placeholder, ",".join([db.placeholder]*len(names)))
            for row in db.executesql(query, [searchForCommon] + [lang_primary] + list(names)):
                if row[0] not in name_to_vern:  # nothing saved yet
                    if row[2]:  # this is a preferred match, and is the first preferred encountered, so is the standard vernacular
                        if row[3]:  # this is a match, so we don't need to store any non-preferred versions
                            name_to_vern[row[0]] = [row[1]]
                        else:  # save space for non-preferred matches: there must be at least one, unless the match was via sciname
                            name_to_vern[row[0]] = [row[1], []]
                    else:  # this is not preferred: no standard vernacular, save as an extra
                        name_to_vern[row[0]] = [None, [row[1]]]
                else:
                    # the entry exists, so we must have already filled out some vernaculars
                    # another match, and standard vernacular didn't match: add to extras
                    if row[3] and len(name_to_vern[row[0]]) == 2:
                        name_to_vern[row[0]][1].append(row[1])
        for tab in results:
            for row in results[tab]:
                try:
                    ott = row[colname_map['ott']]
                    row.extend(ott_to_vern[ott])
                except KeyError:
                    try:
                        name = row[colname_map['name']]
                        row.extend(name_to_vern[name])
                    except:
                        pass  # might reach here if the latin name has matched, but no vernaculars
        return {"headers": colname_map, "leaf_hits": results.get('ordered_leaves'), "node_hits": results.get('ordered_nodes'), "lang": language}
    except:
        return {"headers": colname_map, "leaf_hits": [], "node_hits": [], "lang": language}


# find best vernacular name which matches user's query group by ott.
def findMatchMostName(vernacular_hits, searchFor):
    last_ott = -1
    temp_group = []
    vernacular_hit_res = []
    for row in vernacular_hits:
        if last_ott != row.ott:
            last_ott = row.ott
            if len(temp_group) > 0:
                vernacular_hit_res.append(
                    findMatchMostNameInEachOttGroup(temp_group, searchFor))
            temp_group = []
        temp_group.append(row)
    if len(temp_group) > 0:
        vernacular_hit_res.append(
            findMatchMostNameInEachOttGroup(temp_group, searchFor))
    return vernacular_hit_res


def findMatchMostNameInEachOttGroup(group, searchFor):
    preferred_row = None
    preferred_vernacular = None

    for row in group:
        if row.preferred:
            preferred_row = row
            preferred_vernacular = row.vernacular
            if doesQueryMatchHit(searchFor, row.vernacular):
                return row

    for row in group:
        if doesQueryMatchHit(searchFor, row.vernacular):
            unpreferred_hit = row.vernacular
            row.vernacular = preferred_vernacular
            row.unpreferred_hit = unpreferred_hit
            return row

    if preferred_row is None:
        return group[0]
    else:
        return preferred_row


def doesQueryMatchHit(query, hit):
    wordIndex = 0
    for word in query:
        wordIndex = wordIndex+1
        if word.upper() in hit.upper():
            if wordIndex == len(query):
                return True
        else:
            return False
    return False


def search_for_sponsor():
    """
    Searches OneZoom for sponsorship text

    :something?:`parameter1` And then describe the parameter.

    """
    response.headers["Access-Control-Allow-Origin"] = '*'
    language = request.vars.lang or request.env.http_accept_language or 'en'
    try:
        searchFor = make_unicode(request.vars.query)
        # remove initial punctuation, e.g. we might have been passed in
        searchType = request.vars.type or 'all'
        defaultImages = True if (request.vars.get('default_images')) else False
        order = True if (request.vars.get('sorted')) else False
        limit = request.vars.get('limit')
        start = request.vars.get('start') or 0
        return search_sponsor(searchFor, searchType, language, order, limit, start, defaultImages)
    except:
        if is_testing:
            raise
        else:
            return {'lang': language}


def search_sponsor(searchFor, searchType, language, order_by_recent=None, limit=None, start=0, defaultImages=False):
    from OZfunctions import get_common_names
    if searchFor:
        try:
            lang_primary = language.split(',')[0].split("-")[0].lower()
            searchFor = [s for s in searchFor.replace(
                "%", "").replace("_", " ").split() if s]
            # disallow single letter searching
            if len(searchFor) == 0 or all(len(s) == 1 for s in searchFor):
                return {}
            verified_name = db.reservations.verified_name
            verified_more_info = db.reservations.verified_more_info
            colnames = [
                'OTT_ID', 'name', 'verified_name', 'verified_more_info', 'verified_kind',
                'verified_url', 'verified_preferred_image_src', 'verified_preferred_image_src_id']
            alt_txt = {"verified_name": T("This leaf has been sponsored", language=language),
                       "verified_more_info": T("text awaiting confirmation", language=language),
                       "verified_kind": "",
                       "verified_preferred_image_src": None,
                       "verified_preferred_image_src_id": None,
                       "verified_url": None}
            alt_colnames = [(("'"+alt_txt[c]+"'" if alt_txt[c] else "NULL") +
                             " AS " + c) if c in alt_txt else c for c in colnames]
            colname_map = {nm: index for index, nm in enumerate(colnames)}
            search_query = {'verif': "", 'unverif': ""}
            search_terms = []

            if searchType != "all":
                search_query['verif'] = "verified_kind = " + db.placeholder
                search_query['unverif'] = "user_sponsor_kind = " + \
                    db.placeholder
                search_terms.append(searchType)

            for word in ["%"+w+"%" for w in searchFor if w]:
                if search_terms:
                    search_query['verif'] += " AND "
                    search_query['unverif'] += " AND "
                search_query['verif'] += ("(verified_name like " + db.placeholder +
                                          " or verified_more_info like " + db.placeholder + ")")
                search_query['unverif'] += ("(user_sponsor_name like " + db.placeholder +
                                            " or user_more_info like " + db.placeholder + ")")
                search_terms.extend([word, word])

            # The logic here is complex. We might wish to allow people to search either
            # for their entered text if not yet verified, or their verified text once it
            # appears. If the former, we should put up the holding text in alt_txt.
            # We detect this by looking at verified_time (for verified text) or
            # user_sponsor_kind (for unverified text).
            # We also need to not return expired or otherwise deactivated leaves

            # The verified ones
            query = "SELECT * FROM (SELECT " + \
                ",".join(colnames) + " FROM reservations"
            query += " WHERE verified_time IS NOT NULL AND (deactivated IS NULL OR deactivated = '')"
            query += " AND (DATE_ADD(verified_time, INTERVAL sponsorship_duration_days DAY) > CURDATE())"
            query += " AND " + search_query['verif']
            if order_by_recent:
                query += ' ORDER BY verified_time DESC'
            query += ") AS t1"

            query += " UNION ALL "

            query += "SELECT * FROM (SELECT " + \
                ",".join(alt_colnames) + " FROM reservations"
            query += " WHERE verified_time IS NULL AND user_sponsor_kind IS NOT NULL AND user_sponsor_kind != ''"
            query += " AND (deactivated IS NULL OR deactivated = '')"
            query += " AND " + search_query['unverif']
            if order_by_recent:
                query += ' ORDER BY user_updated_time DESC'
            query += ") AS t2"

            if limit:
                query += ' LIMIT ' + str(int(limit))
                if start:
                    query += ' OFFSET ' + str(int(start))

            reservations = db.executesql(query, search_terms + search_terms)

            reservationsOttArray = []
            for row in reservations:
                reservationsOttArray.append(row[colname_map['OTT_ID']])

            query = db.ordered_leaves.ott.belongs(reservationsOttArray)
            leaves = db(query).select(
                db.ordered_leaves.id, db.ordered_leaves.ott)

            language = request.vars.lang or request.env.http_accept_language or 'en'
            common_names = get_common_names(
                reservationsOttArray, lang=language)

            if defaultImages:
                return {"common_names": common_names, "lang": language, "reservations": reservations,  "leaves": leaves, "headers": colname_map, "default_images": {row.ott: [row.src, row.src_id] for row in db(db.images_by_ott.ott.belongs(reservationsOttArray) & (db.images_by_ott.best_any == True)).select(db.images_by_ott.ott, db.images_by_ott.src, db.images_by_ott.src_id, orderby=~db.images_by_ott.src)}}
            else:
                return {
                    "common_names": common_names, "lang": language,
                    "reservations": reservations, "leaves": leaves, "headers": colname_map}

        except:
            if is_testing:
                raise
    return {}


def get_ids_by_ott_array():
    """
    Map a comma-separated list of otts (e.g. popular species) to the leaf (or node) IDs.
    Returns {'leaves':leaf_map, 'nodes':node_map, 'names':name_map} where leaf_map et al
    are dicts of ott:id or ott:sciname mappings (scientific names are returned as
    this is cheap to do)
    """
    session.forget(response)
    response.headers["Access-Control-Allow-Origin"] = '*'
    return ids_from_otts_string(request.vars.ott_array or "")


def otts2vns():
    '''
    Used e.g. to fill out the popular species lists,
    can call with request.vars.lang=XX and with prefer_short=1
    Will return nulls for unmatched otts if return_nulls=1
    Returns e.g. {"770315":"Human","872567":"Brown Bear", "lang":"en-gb"}
    '''
    session.forget(response)
    from OZfunctions import get_common_names
    response.headers["Access-Control-Allow-Origin"] = '*'
    lang = request.vars.lang or request.env.http_accept_language or 'en'
    try:
        ret_otts = get_common_names([int(x) for x in request.vars.otts.split(',')],
                                    return_nulls=True if request.vars.nulls else False,
                                    prefer_short_name=True if request.vars.prefer_short else False,
                                    include_unpreferred=True if (
                                        request.vars.include_unpreferred or request.vars.all) else False,
                                    return_all=True if request.vars.all else False,
                                    lang=lang)
        ret_otts['lang'] = lang
        return ret_otts
    except (AttributeError, ValueError):
        return {'lang': lang}


def update_visit_count():
    session.forget(response)
    response.headers["Access-Control-Allow-Origin"] = '*'
    try:
        if request.vars.api_hits:
            values = []
            for ott in request.vars.api_hits.split(","):
                values.append("(" + ott + ",1,0,0)")
            values = ",\n".join(values)
            query = "insert into visit_count (ott, detail_fetch_count, search_count, leaf_click_count) values \n" + values + "\n"
            query = query + "on duplicate key update detail_fetch_count = detail_fetch_count + 1"
            db.executesql(query)

        if request.vars.search_hits:
            values = []
            for ott in request.vars.search_hits.split(","):
                values.append("(" + ott + ",0,1,0)")
            values = ",\n".join(values)
            query = "insert into visit_count (ott, detail_fetch_count, search_count, leaf_click_count) values \n" + values + "\n"
            query = query + "on duplicate key update search_count = search_count + 1"
            db.executesql(query)

        if request.vars.leaf_click_count:
            values = []
            for ott in request.vars.leaf_click_count.split(","):
                values.append("(" + ott + ",0,0,1)")
            values = ",\n".join(values)
            query = "insert into visit_count (ott, detail_fetch_count, search_count, leaf_click_count) values \n" + values + "\n"
            query = query + "on duplicate key update leaf_click_count = leaf_click_count + 1"
            db.executesql(query)

        return {"status": "success"}
    except:
        return {"status": "failure"}


def get_id_by_ott():
    session.forget(response)
    response.headers["Access-Control-Allow-Origin"] = '*'
    ott = request.vars.ott
    query = db.ordered_nodes.ott == ott
    result = db(query).select(db.ordered_nodes.id, db.ordered_nodes.ott)
    if len(result) > 0:
        return {"id": result[0].id}
    else:
        query = db.ordered_leaves.ott == ott
        result = db(query).select(db.ordered_leaves.id, db.ordered_leaves.ott)
        if len(result) > 0:
            return {"id": -result[0].id}
    return {"id": "none"}

# A few convenience pages not used by the OneZoom viewer, which return JSON data about various identifiers, children, etc.


def getOTT():
    """ this is called as a json request with potentially multiple identifiers, e.g.
        http://mysite/getOTT.json?eol=123&eol=456&ncbi=789 
        and should return the OTT ids and scientific names  EOLid in JSON form: {'data':'5678'}

        This is useful for common-name searching, where the EoL search API returns EOL identifiers
        which can then be matched against OneZoom leaves.
    """
    sources = ["eol", "ncbi", "iucn"]
    data = {}
    from numbers import Number
    try:
        for s in sources:
            if s in request.vars:
                if isinstance(request.vars[s], basestring) or isinstance(request.vars[s], Number):
                    # put it in an array anyway
                    id_list = [int(request.vars[s])]
                else:
                    id_list = [int(id) for id in request.vars[s]]
                response.flash = id_list
                rows = db(db.ordered_leaves[s].belongs(id_list)).select(
                    db.ordered_leaves[s], db.ordered_leaves.ott)
                data[s] = {r[s]: r.ott for r in rows}
        return(dict(data=data, errors=[]))
    except ValueError:
        return(dict(data=None, errors=["Some of the passed-in ids could not be converted to numbers"]))


def children_of_OTT():
    """ Return a set of terminal nodes for this OTT taxon: easily done using the nested set representation. The URL is of the form
        http://mysite/children_of_OTT.json/<OTT>?sort=<sortcol>&max=<max>&page=1 which returns <max> leaves sorted by <sortcol>, e.g.
        http://mysite/children_of_OTT.json/13943?sort=popularity&max=10. The parameters <sortcol>, <max> and <page> are optional, with defaults
        <sortcol> = id, <max> = 50 and <page>=1. if <max> is greater than 1000 it is set to 1000, to avoid responding with huge queries.
        The JSON returned should have the ott, name (scientific name), eol, wikidataQ, and popularity  
    """
    try:
        OTTid = int(request.args[0])
        query = child_leaf_query('ott', OTTid)
        query = query & (db.ordered_leaves.eol != None)
        rows = select_leaves(query,
                             request.vars.get('page'),
                             request.vars.get('max'),
                             request.vars.get('sort'))
        return(dict(data={'rows': rows.as_list(), 'EOL2OTT': {r.eol: r.ott for r in rows}}))
    except ValueError:  # probably bad int inputted
        return(dict(errors=['OTT id must be an integer'], data=None))


def children_of_EOL():
    """ Return a set of terminal nodes for this OTT taxon: easily done using the nested set representation. The URL is of the form
        http://mysite/descendant_leaves.json/<OTT>?sort=<sortcol>&max=<max>&page=1 which returns <max> leaves sorted by <sortcol>, e.g.

        http://mysite/descendant_leaves.json/2684257?sort=popularity&max=10. The parameters <sortcol>, <max> and <page> are optional, with defaults
        <sortcol> = id, <max> = 50 and <page>=1. if <max> is greater than 1000 it is set to 1000, to avoid responding with huge queries.
        The JSON returned should have the ott, name (scientific name), eol, wikidataQ, and popularity  
    """
    try:
        EOLid = int(request.args[0])
        query = child_leaf_query('eol', EOLid)
        query = query & (db.ordered_leaves.eol != None)
        rows = select_leaves(query,
                             request.vars.get('page'),
                             request.vars.get('max'),
                             request.vars.get('sort'))
        return(dict(data={'EOL2OTT': {r.eol: r.ott for r in rows}}))
    except ValueError:  # probably bad int inputted
        return(dict(errors=['EOL id must be an integer'], data=None))


def select_leaves(query, page=None, limit=None, sortcol=""):
    """ Selects on a query. If 'sortcol' is entered as uppercase, sort descending (requires all sortable cols to be lowercase names) """
    limitby = (0, 40)
    orderby = ""
    try:
        select = [db.ordered_leaves[field]
                  for field in ['ott', 'name', 'eol', 'wikidata', 'popularity']]
        page = int(page or 1)
        limit = min(int(limit or limitby[1]), 1000)
        limitby = (limit*(page-1), limit*page)
        if sortcol.lower() in db.ordered_leaves.fields:
            if sortcol.lower() == sortcol:
                orderby = "ordered_leaves." + sortcol.lower()
            else:
                orderby = "ordered_leaves." + sortcol.lower() + " DESC"
    except:
        pass
    return db(query).select(limitby=limitby, orderby=orderby, *select)


# PRIVATE FUNCTIONS

def make_unicode(input):
    try:
        if input and type(input) != unicode:
            input = input.decode('utf-8')
    except NameError:
        pass  # for python3
    return input
