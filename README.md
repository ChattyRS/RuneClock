# RuneClock

RuneClock is a general-purpose Discord bot for RuneScape Discord servers, originally written for the [Portables Discord server](https://discord.gg/QhBCYYr).

## Usage

* Invite the bot to your server using the [invite link](https://discordapp.com/api/oauth2/authorize?client_id=449462150491275274&permissions=8&scope=bot%20applications.commands). Replace the permission number in the url if you want to invite the bot with different permissions. Note that some features may not work if the appropriate permissions are not granted.
* When the bot is joined to your server, the default command prefix will be a dash ("-"). You can change this prefix using the `prefix` command.
* For any further information regarding commands, please use the `help` command.
* Feel free to join the [support server](https://discord.gg/Pcbz2HH) for any help or questions!

## Authors

* **@schattie** on Discord

## Software and installation

* [Python 3.12](https://www.python.org/)
* [PostgreSQL 16](https://www.postgresql.org/)
* [Discord.py v2.4](https://github.com/Rapptz/discord.py)

After installing Python, you can install the remaining dependencies as follows:
```
$ pip install -r requirements.txt
```
* [discord.py v2.4](https://github.com/Rapptz/discord.py)
* [SQLAlchemy](https://www.sqlalchemy.org/)
* [asyncpg](https://github.com/MagicStack/asyncpg)
* [gspread_asyncio](https://github.com/dgilman/gspread_asyncio)
* [NumPy](http://www.numpy.org/)
* [matplotlib](https://matplotlib.org/)
* [SymPy](https://www.sympy.org/en/index.html)
* [oauth2client](https://oauth2client.readthedocs.io/en/latest/)
* [psutil](https://psutil.readthedocs.io/en/latest/)
* [pytz](https://pypi.org/project/pytz/)
* [validators](https://validators.readthedocs.io/en/latest/)
* [PRAW](https://praw.readthedocs.io/en/latest/)
* [feedparser](https://pythonhosted.org/feedparser/)
* [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
* [lxml](https://lxml.de/)
* [imageio](https://github.com/imageio/imageio)
* [PyGithub](https://github.com/PyGithub/PyGithub)

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details

## Privacy policy

In short, RuneClock only ever stores any data when explicitly requested to do so by a user.
Any stored data is immediately deleted when it is no longer required, and/or can be deleted by the user who requested to store it.

See the [PRIVACY_POLICY.md](PRIVACY_POLICY.md) file for details.