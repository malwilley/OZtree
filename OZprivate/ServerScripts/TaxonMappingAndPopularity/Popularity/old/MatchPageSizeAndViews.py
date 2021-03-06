#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
Call as:

    MatchPageviews.py prefix pagetitles.txt XXwiki-NNNNNNNN-page.sql.gz pagecounts+++-totals.bz2 pagecounts+++-totals.bz2, ...

INPUT:

prefix denotes the name used for the appropriate wiki project, e.g. 'en.z' for en.wikipedia (note this is different from the normal dumps, which just use 'en')
'The project is one of b (wikibooks), k (wiktionary), n (wikinews), o (wikivoyage), q (wikiquote), s (wikisource), v (wikiversity), z (wikipedia).'

pagetitles.txt gives the page titles (spaces are substituted for _, and cgi-escapes done). Any text before the last tab is taken as a row name, to output
any number of pagecounts files can be provided, and the page visits in each file added to the output. In particular, you might want to pass in a list of
pagetitles as generated by OTT_2_Wikidata.py (see example below)

XXwiki-NNNNNNNN-page.sql.gz is the SQL database dump, from http://dumps.wikimedia.org/ (listed as Base per-page data (id, title, old restrictions, etc).)
This should match the wiki denoted by the 'prefix' value. So for instance if you put prefix = 'en.z', you should use an sql page dump of the enlish wikipedia
such as https://dumps.wikimedia.org/enwiki/latest/enwiki-latest-page.sql.gz

The pagecount files per month are probably the most sensible, and can be obtained from http://dumps.wikimedia.org/other/pagecounts-ez/merged/. The per-month files
end in totals.bz2

OUTPUT:

you might want to take a quick look at the top rated taxa. For example, if a single pageview file is given then you can look at the 3rd column

sort -k 3,3nr -t$'\t' popularity.txt | less

or for something more complicated, use R

> dat <- read.delim("popularity.txt")
> viewcols <- grep('bz2',names(dat))
> dat$trmeanMonthlyPageviews <- apply(dat[,viewcols],1,function(x) mean(sort(x, TRUE)[-1:-2])) #trim off the top 2 months, to kill spikes
> dat[order(dat$trmeanMonthlyPageviews, decreasing=TRUE),][1:40,-viewcols]
> dat[order(dat$page_size, decreasing=TRUE),][1:40,-viewcols]
> dat[order(dat$trmeanMonthlyPageviews*dat$page_size, decreasing=TRUE),][1:40,-viewcols]

EXAMPLES:

OneZoomTouch/server_scripts/OTT_2_Wikidata.py ott/taxonomy.tsv wikidumps/wikidata-20151005-all.json.gz enwiki > map_file.txt
cut -f 1,4 map_file.txt | sort -n | uniq | MatchPageSizeAndViews.py en.z - wikidumps/enwiki-latest-page.sql.gz wikidumps/pagecounts-*totals.bz2 > OneZoomTouch/popularity.txt

'''

import sys
import csv
import re
import resource
import fileinput
import collections
import urllib.parse

def warn(*objs):
    print(*objs, file=sys.stderr)

def memory_usage_resource():
    import resource
    rusage_denom = 1024.
    if sys.platform == 'darwin':
        # ... it seems that in OSX the output is different units ...
        rusage_denom = rusage_denom * rusage_denom
    mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / rusage_denom
    return mem

def sensible_sum(l):
    '''Treat None as NA, e.g. if l==[] or l == [None, None] return None'''
    l = [x for x in l if x is not None]
    if len(l):
        return sum(l)
    else:
        return None

def strNone(x):
    return str(x) if x is not None else ''

if len(sys.argv) < 4:
    sys.exit('Provide the name of a wiki project (e.g. en.z, or en.b) as the first argument, the name of a titles file as the second, and pagecounts files as further args')

linetitles={}

#we collect the original lines in the tsv file in each element of 'lines', the page size data in each element of 'pagesize' and 
# the vector of view stats in arrays stored in each element of 'pageviews'
lines = []
pagesize = []
pageviews = []
title_col=-1 #the column in the tsv file which contains the wiki title (default = last column)

pageview_files = collections.OrderedDict()
for fn in sys.argv[4:]:
    if fn not in pageview_files: #make unique
        pageview_files[fn]=len(pageview_files)
try:
    title_file = fileinput.input(sys.argv[2])
except IOError as e:
    sys.exit("I/O error reading list of page titles ({0}): {1}".format(e.errno, e.strerror))
    
for line in title_file:
    if (title_file.filelineno() % 500000 == 0):
        warn("{} entries read from title file: mem usage {} Mb".format(title_file.filelineno(), memory_usage_resource()))
    line = line.rstrip('\r\n')
    lines.append(line)
    if title_file.isfirstline():
        
        pagesize.append("page_size")
        pageviews.append(list(pageview_files.keys())) #headers
    else:
        wikititle = line.rsplit("\t",1)[title_col] #assume 2nd item in each row is the page title
        pagesize.append(None)
        if wikititle != "":
            wikititle = wikititle.replace(" ","_")
            linetitles[wikititle] = len(lines)-1
            pageviews.append([None] * len(pageview_files))
        else:
            pageviews.append([])
warn("Done: {} entries read.".format(len(lines)))

try:
    import gzip
    import csv    #use csv reader as it copes well e.g. with escaped SQL quotes in fields etc.
    pagelen_file = csv.reader(gzip.open("/Volumes/SDdisk/PageCounts/enwiki-latest-page.sql.gz", 'rt', encoding='utf-8'), quotechar='\'',doublequote=True)
except IOError as e:
    sys.exit("I/O error reading sql dump of page info ({0}): {1}".format(e.errno, e.strerror))
#the column numbers for each datum are specified in the SQL file, and hardcoded here.
page_table_namespace_column = 2
page_table_title_column = 3
page_table_pagelen_column = 12
match_line = "INSERT INTO `page` VALUES" #pageviews have project name (ascii) followed by space, followed by uri-escaped title, followed by space, followed by integer
for fields in filter(lambda x: False if len(x)==0 else x[0].startswith(match_line), pagelen_file):
    if (pagelen_file.line_num % 500 == 0):
        warn("{} lines ({} pages) read from page info SQL file: mem usage {} Mb".format(pagelen_file.line_num,pagelen_file.line_num*1000, memory_usage_resource()))
    field_num=0
    for f in fields:
        try:
            if f.lstrip()[0]=="(":
                field_num=0
                namespace = None
                title = None
        except IndexError:
            pass
        field_num+=1;
        if field_num== page_table_namespace_column:
            namespace = f
        if field_num== page_table_title_column:
            title = f
        elif field_num==page_table_pagelen_column and namespace == '0':
            try:
                pagesize[linetitles[title]] = f
            except LookupError:
                pass

#page titles in the pageview dumps are uri-escaped, so we need to change the keys to escaped ones, to check against pageviews
for t in linetitles:
    linetitles[urllib.parse.quote(t)] = linetitles.pop(t)


match_project = (sys.argv[1]+" ").encode() #pageviews have project name (ascii) followed by space, followed by uri-escaped title, followed by space, followed by integer
try:
    fp = fileinput.input(pageview_files,openhook=fileinput.hook_compressed)
except IOError as e:
    sys.exit("I/O error reading pageview dumps ({0}): {1}".format(e.errno, e.strerror))

old_filename = ''
filenum = -1
problem_lines = {x:[] for x in pageview_files} #there are apparently some errors in the unicode dumps
for line in fp:
    if (fp.filelineno() % 1000000 == 0):
        warn("{} entries read from pagecount file {} ({}): mem usage {} Mb".format(fp.filelineno(), pageview_files[fp.filename()], fp.filename(), memory_usage_resource()))
    if line.startswith(match_project):
        try:
            fields = line.decode('UTF-8').rstrip('\r\n').split(" ")
            pageviews[linetitles[fields[1]]][pageview_files[fp.filename()]] = int(fields[2])
        except LookupError:
            pass
        except UnicodeDecodeError:
            problem_lines[fp.filename()].append(fp.filelineno())
for fn,prob_lines in problem_lines.items():
    if len(prob_lines):
        warn("Problem decoding certain lines in {}. The following lines have been ignored: {}.".format(fn, ", ".join([str(x) for x in prob_lines])))
            
            
firstline = 1
for line, size, vals in zip(lines, pagesize, pageviews):
    if len(pageview_files)>1:
        if firstline:
            print("\t".join([line] + [size] + vals + ['total_pageviews']))
            firstline = 0
        else:
            print("\t".join([line] + [strNone(size)] + list(map(strNone,vals)) + [strNone(sensible_sum(vals))]))
    else:
        print("\t".join([line] + [strNone(size)] + list(map(strNone,vals))))