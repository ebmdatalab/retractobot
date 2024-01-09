## Structure

The management commands do all the work:

* `get_pubmed_retractions`: searches PubMed for retractions and retraction notices, adds newly retracted papers to the database
* `get_scopus_citations`: uses Scopus APIs to search for papers that cite retracted papers, adds new citing papers to the database.
* `get_missing_citation_metadata`: uses Scopus and Pubmed APIs to fill any missing CitingPaper metadata, including title, publication date, and authors. This can be run at any time, but usually after new citations have been fetched.
* `update_comparison_date`: applies our date selection protocol to available dates (journal and electronic from pubmed and scopus) and uploads it to the database for more efficienct querying. `contactable_authors` and `randomise` both depend on the comparisondate field, so they automatically call this before running.
* `contactable_authors` : takes the authors from the citing paper, optionally uses Scopus to get author information for retracted papers (this can be used to filter out self-citations) and populates contactable authors on the citation retraction pairs. Run after getting citations so the retracted papers have a scopus id. The RCT depends on a populated contactable author field, so `randomise set_randomisation` automatically calls this (without querying scopus for retracted authors) before running. Retracted authors should be collected from scopus at least once before running.
* `randomise` : apply inclusion/exclusion criteria and randomise papers, updating the database and setting up the RCT. Also used to generate simulations with historical data without updating the database for assessing model fit.
* `send_retraction_emails`: for all retracted papers included in trial, sends retraction alert mails to any authors who haven't previously received them, defaults to a dry run, has a test mode
* `retrieve_mailgun_events`: command to retrieve data on events in emails, and save them to database.


## First time environment set-up

### Prerequisites
- **Python v3.10.x**
- **virtualenv**
- **Postgres**
- **just**

This project has been tested with python3.10. If python3.10 is not on the system, then it should be installed.

```sh
add-apt-repository ppa:deadsnakes/ppa
apt-get update
apt-get install python3.10 python3.10-venv
```

`just` is not currently available in apt, so follow the instructions on the [just](https://github.com/casey/just) page.

**Set up a postgres database**

After installing postgres, a root user will need to change the password for the postgres user, then use the postgres user create a database and grant privileges.

```sh
psql -U postgres -h localhost -c "CREATE DATABASE retractobot"
```

On Linux, you'll need to create the user with relevant permissions:
```
psql -U postgres -h localhost -c "
CREATE ROLE retractobot PASSWORD 'PASSWORD HERE' NOSUPERUSER CREATEDB LOGIN;
GRANT ALL PRIVILEGES on database retractobot to retractobot;
"
```

Then load a database dump into the local postgres instance with the retractobot user.

```sh
pg_restore -U retractobot -h localhost --clean --if-exists --no-acl --no-owner -d retractobot retractobot.dump
```

**Clone github repo**

Check out the most recent version of this code with a git clone

Copy `environment-sample` to `environment` and update the necessary api keys.

Update `RETR_DB_PASS` with the password provided when creating the retractobot user.

The just commands should be run from within the git directory (the same level
as the justfile).

```sh
just devenv
```

This creates the virtual environment with python 3.10 and installs dependencies

**Check migrations:**
```sh
just check-migrations
```

**Run tests**
```sh
just test
```
This is done via a custom version of the `test` command, which sets
logging based on `-v` parameters. You can do `-v 2` to seen warnings
or `-v 3` for lots of debug logging. Note that exceptions are a normal
part of the tests, and will be shown.


## Running the RCT

The option to the management command `randomise` called `set_randomisation`
puts all papers in the appropriate group by setting the `rct_group` field on
the `retracted_paper` table as follows:

* 'x' for excluded - for example, no emails are known for any authors of citing papers, so excluded from trial
* 'c' for control - randomly chosen to be in the control group of the trial by stratified randomisation, so not sent or to be sent emails
* 'i' for intervention - randomly chosen to be in the intervention group of the trial by stratified randomisation, so sent and to be sent emails
* None - either no attempt yet to send mails for this paper so state unknown, not in the RCT at all

The field `exclusion_reason` is present only if the paper is in the excluded
group 'x', when it gives the reason for exclusion.

### Final scrape before RCT

The `RETR_LOG_FILE` environment var should be set to the preferred directory
in order to save the output of the trial set-up.

```sh
just run get_pubmed_retractions
just run get_scopus_citations -v 2
just run get_missing_citation_metadata --scopus-only --batch 250 --skip-errors -v 2
just run get_missing_citation_metadata --pubmed-only --batch 250 --skip-errors -v 2
just run contactable_authors --get-retracted-authors --batch 250 -v 2
just run randomise -v 2 update_exclusions
```

### Set the RCT status

This is only done once, and sets all current papers to be in the RCT, so only
do it when confident the data scraped looks good.

```sh
just run randomise -v 2 set_randomisation
```

After randomisation has been done, archive the log file by copying it to
a new file.

And make a backup of the database.
```sh
pg_dump -U postgres -h localhost -Fc retractobot > retractobot_post_randomisation.dump
```

Count the number of papers that have been put in each group:
```sh
just run flowchart
```
Further detail on the balance of characteristics can be found by running:
```sh
just run randomise set_randomisation --just-check
```

**Warning:** AFTER RANDOMISING, DO NOT COLLECT RETRACTIONS AGAIN AND DO NOT TRY TO UPDATE EXCLUSIONS OR COLLECT CONTACTABLE AUTHORS

### Sending mails

To do a dry run email send, run the following command. There are three levels of
verbosity set by `-v`, to see what is happening use level 2.

```sh
just run send_retraction_emails -v 2
```

It won't write to the database or send any emails unless you add the
`--live-run` switch - you just get to see what it would do.

For development, you can test the database writing and email sending
without actually mailing any academics by sending the live run emails to a test
address with `--test-email`.

```sh
just run --test-email xxxxxxxx@xxxxx.com -v 2 --live-run
```

Of course if you do test email run, it does log that sending was successful
to the database...


#### Do a test run

```sh
just run send_retraction_emails --limit=100
```

The emails sent are put in a local mailbox.

```sh
mutt -f debug-last-sent-mails.mbox
```

Check the copy looks good. You can "bounce" (forward without
changing any headers or details, with "B" in mutt) the messages
elsewhere for checking in different email clients.

#### Do initial live batch

This is the first pilot send of real mails. We do the run for the first 100
authors (ordered by AUID).

This command doesn't do any logging, as it is the raw internal command
(so we can set limit).

```sh
just run send_retraction_emails --live-run --limit=100 -v 3
```
Check the log for any errors.

Check email service provider logs that the mails are really being sent and
everything looks OK.

#### Send all mails

Every two days, if everything is OK, run again with the limit
increased to double.

```sh
just run send_retraction_emails --live-run --limit=200 -v 3
```

#### Retrieve mailgun events

Set up a cronjob so that mailgun logs will be added to the database every day.
Mailgun logs are stored for a few days, but in case the server is down, we do
not want to skip a day.

This would get the logs once a day at 4am
```sh
00 04 * * * /home/retractobot-project/retractobot/deploy/get_mailgun_events.sh
```

## After the trial
Once the follow-up time has ended

- Make a back-up of the database
```sh
pg_dump -U postgres -h localhost -Fc retractobot > retractobot_post_rct.dump
```

**Warning:** DO NOT COLLECT RETRACTIONS AGAIN AND DO NOT TRY TO UPDATE EXCLUSIONS OR COLLECT CONTACTABLE AUTHORS

- Collect new scopus citations
```
just run get_scopus_citations -v 2
just run get_missing_citation_metadata --scopus-only --batch 250 --skip-errors -v 2
just run get_missing_citation_metadata --pubmed-only --batch 250 --skip-errors -v 2
```

Generate the analysis dataset

```sh
just run randomise gen_dataset --follow-up-date `DATE_EMAILS_FINISHED` --output-file retractobot_trial.csv
```
This assumes we will count any citations that happened in 2024 and only had a publication year (no month or day) as not part of the trial.


## Delete email addresses
Email addresses are stored in 2 places in the database: the AuthorAlias and MailSent objects.

```
just run shell
from retractions.models import AuthorAlias, MailSent
AuthorAlias.objects.update(email_address=None)
MailSent.objects.update(to=None)
```

Because this removes email addresses, which are relied upon for computing the `count_unique` of contactable authors, this should be run after `gen_dataset` has been run.
Otherwise, care should be taken that neither `contactable_authors` nor `randomise update_exclusions` should be run, as those would recompute the randomisation strata.
