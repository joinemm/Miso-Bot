import asyncio
import json
import os
import random
import re

import aiohttp
import arrow
import async_cse
import discord
import regex
import tweepy
from bs4 import BeautifulSoup
from discord.ext import commands, flags
from modules import exceptions, util
from random_user_agent.user_agent import UserAgent
from tweepy import OAuthHandler

TWITTER_CKEY = os.environ.get("TWITTER_CONSUMER_KEY")
TWITTER_CSECRET = os.environ.get("TWITTER_CONSUMER_SECRET")
IG_COOKIE = os.environ.get("IG_COOKIE")
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET")
GOOGLE_API_KEY = os.environ.get("GOOGLE_KEY")
ROTATING_PROXY_URL = os.environ.get("ROTATING_PROXY_URL")
GCS_DEVELOPER_KEY = os.environ.get("GOOGLE_KEY")


class Media(commands.Cog):
    """Fetch various media"""

    def __init__(self, bot):
        self.bot = bot
        self.icon = "🌐"
        self.twitter_api = tweepy.API(OAuthHandler(TWITTER_CKEY, TWITTER_CSECRET))
        self.google_client = async_cse.Search(GCS_DEVELOPER_KEY)
        self.ig_colors = [
            int("405de6", 16),
            int("5851db", 16),
            int("833ab4", 16),
            int("c13584", 16),
            int("e1306c", 16),
            int("fd1d1d", 16),
            int("f56040", 16),
            int("f77737", 16),
            int("fcaf45", 16),
        ]
        self.regions = {
            "kr": "www",
            "korea": "www",
            "eune": "eune",
            "euw": "euw",
            "jp": "jp",
            "japan": "jp",
            "na": "na",
            "oceania": "oce",
            "oce": "oce",
            "brazil": "br",
            "las": "las",
            "russia": "ru",
            "ru": "ru",
            "turkey": "tr",
            "tr": "tr",
        }
        self.user_agents = UserAgent()

    @commands.group(aliases=["league"], case_insensitive=True)
    async def opgg(self, ctx):
        """League of legends stats."""
        await util.command_group_help(ctx)

    @opgg.command()
    async def profile(self, ctx, region, *, summoner_name):
        """See your op.gg profile."""
        parsed_region = self.regions.get(region.lower())
        if parsed_region is None:
            return await ctx.send(f":warning: Unknown region `{region}`")

        region = parsed_region

        ggsoup = GGSoup()
        await ggsoup.create(region, summoner_name)

        if ggsoup.soup.find("div", {"class": "SummonerNotFoundLayout"}):
            raise exceptions.Warning("Summoner not found!")

        content = discord.Embed()
        content.set_author(
            name=f"{ggsoup.text('span', 'Name')} [{region.upper()}]",
            icon_url=ggsoup.src("img", "ProfileImage"),
        )

        rank = ggsoup.text("div", "TierRank")
        lp = ""
        wins_losses = ""
        if rank != "Unranked":
            lp = ggsoup.text("span", "LeaguePoints")
            wins_losses = (
                f"{ggsoup.text('span', 'wins')} {ggsoup.text('span', 'losses')} "
                f"({ggsoup.text('span', 'winratio').split()[-1]})"
            )

        content.add_field(
            name="Rank",
            value=f"**{rank}**"
            + (f" {lp} **|** {wins_losses}" if rank != "Unranked" else ""),
            inline=False,
        )

        rank_image = "https:" + ggsoup.soup.find("div", {"class": "Medal"}).find(
            "img"
        ).get("src")
        content.set_thumbnail(url=rank_image)
        content.colour = int("5383e8", 16)

        champions = []
        for championbox in ggsoup.soup.findAll("div", {"class": "ChampionBox"}):
            name = championbox.find("div", {"class": "ChampionName"}).get("title")
            played_div = championbox.find("div", {"class": "Played"})
            played_count = played_div.find("div", {"class": "Title"}).text.strip()
            winrate = played_div.find("div", {"class": "WinRatio"}).text.strip()
            champions.append(
                f"**{played_count.replace(' Played', '** Played')} **{name}** ({winrate})"
            )

        content.add_field(
            name="Champions", value="\n".join(champions) if champions else "None"
        )

        match_history = []
        for match in ggsoup.soup.findAll("div", {"class": "GameItem"}):
            gametype = ggsoup.text("div", "GameType", match)
            champion = (
                match.find("div", {"class": "ChampionName"}).find("a").text.strip()
            )
            win = match.get("data-game-result") == "win"
            kda = "".join(
                ggsoup.text("div", "KDA", match.find("div", {"class": "KDA"})).split()
            )
            emoji = ":blue_square:" if win else ":red_square:"
            match_history.append(f"{emoji} **{gametype}** as **{champion}** `{kda}`")

        content.add_field(
            name="Match History",
            value="\n".join(match_history) if match_history else "No matches found",
        )

        await ctx.send(embed=content)

    @opgg.command()
    async def nowplaying(self, ctx, region, *, summoner_name):
        """Show your current game."""
        parsed_region = self.regions.get(region.lower())
        if parsed_region is None:
            return await ctx.send(f":warning: Unknown region `{region}`")

        region = parsed_region

        content = discord.Embed(title=f"{summoner_name} current game")

        ggsoup = GGSoup()
        await ggsoup.create(region, summoner_name, sub_url="spectator/")

        error = ggsoup.soup.find("div", {"class": "SpectatorError"})
        if error:
            raise exceptions.Warning(error.find("h2").text)

        blue_team = ggsoup.soup.find("table", {"class": "Team-100"})
        red_team = ggsoup.soup.find("table", {"class": "Team-200"})
        for title, team in [("Blue Team", blue_team), ("Red Team", red_team)]:
            rows = []
            players = team.find("tbody").findAll("tr")
            for player in players:
                champion = (
                    player.find("td", {"class": "ChampionImage"})
                    .find("a")
                    .get("href")
                    .split("/")[2]
                )
                summoner = ggsoup.text("a", "SummonerName", player)
                url = f"https://{region}.op.gg/summoner/userName={summoner.replace(' ', '%20')}"
                rank = ggsoup.text("div", "TierRank", player)
                rows.append(f"`{rank:20} |` [{summoner}]({url}) as **{champion}**")

            content.add_field(name=title, value="\n".join(rows), inline=False)

        await ctx.send(embed=content)

    @commands.command(aliases=["yt"])
    async def youtube(self, ctx, *, query):
        """Search videos from youtube."""
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "key": GOOGLE_API_KEY,
            "part": "snippet",
            "type": "video",
            "maxResults": 25,
            "q": query,
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 403:
                    raise exceptions.Error("Daily youtube api quota reached.")

                data = await response.json()

        if not data.get("items"):
            return await ctx.send("No results found!")

        await util.paginate_list(
            ctx,
            [
                f"https://youtube.com/watch?v={item['id']['videoId']}"
                for item in data.get("items")
            ],
            use_locking=True,
            only_author=True,
            index_entries=True,
        )

    @flags.add_flag("urls", nargs="+")
    @flags.add_flag("-d", "--download", action="store_true")
    @flags.command(aliases=["ig", "insta"])
    async def instagram(self, ctx, **options):
        """Get all the images from one or more instagram posts."""
        async with aiohttp.ClientSession() as session:
            for url in options["urls"]:
                result = regex.findall("/(p|reel)/(.*?)(/|\\Z)", url)
                if result:
                    url = f"https://www.instagram.com/p/{result[0][1]}"
                else:
                    url = f"https://www.instagram.com/p/{url.strip('/').split('/')[0]}"

                headers = {
                    "User-Agent": self.user_agents.get_random_user_agent(),
                    "X-IG-App-ID": "936619743392459",
                    "Cookie": "ig_cb=2; ig_did=CD9C9CD6-A65D-4CA0-A810-DA55EF09C143; csrftoken=du0pHNPkxq5hpQTiFhWVefvZ01aneHYa; mid=X67owAAEAAHD89ozXg9Fx48IPef0; ds_user_id=5951951432; sessionid=5951951432%3A0eHKUlAtGE83k1%3A13; fbm_124024574287414=base_domain=.instagram.com; shbid=10480; shbts=1618475928.6377892; rur=RVA",
                }
                post_id = url.split("/")[-1]
                newurl = "https://www.instagram.com/graphql/query/"
                params = {
                    "query_hash": "505f2f2dfcfce5b99cb7ac4155cbf299",
                    "variables": '{"shortcode":"'
                    + post_id
                    + '","include_reel":false,"include_logged_out":true}',
                }

                async with session.get(
                    newurl, params=params, headers=headers, proxy=ROTATING_PROXY_URL
                ) as response:
                    try:
                        data = await response.json()
                    except aiohttp.ContentTypeError:
                        raise exceptions.Error(
                            "Instagram has blocked me from accessing their content. Please try again later."
                        )
                    data = data["data"]["shortcode_media"]

                if data is None:
                    await ctx.send(f":warning: Invalid instagram URL `{url}`")
                    continue

                medias = []
                try:
                    for x in data["edge_sidecar_to_children"]["edges"]:
                        medias.append(x["node"])
                except KeyError:
                    medias.append(data)

                avatar_url = data["owner"]["profile_pic_url"]
                username = data["owner"]["username"]
                content = discord.Embed(color=random.choice(self.ig_colors))
                content.set_author(name=f"@{username}", icon_url=avatar_url, url=url)

                if not medias:
                    await ctx.send(f":warning: Could not find any media from `{url}`")
                    continue

                if options["download"]:
                    # send as files
                    async with aiohttp.ClientSession() as session:
                        await ctx.send(f"<{url}>")
                        timestamp = arrow.get(data["taken_at_timestamp"]).format(
                            "YYMMDD"
                        )
                        for n, file in enumerate(medias, start=1):
                            if file.get("is_video"):
                                media_url = file.get("video_url")
                                extension = "mp4"
                            else:
                                media_url = file.get("display_url")
                                extension = "jpg"

                            filename = (
                                f"{timestamp}-@{username}-{post_id}-{n}.{extension}"
                            )
                            async with session.get(media_url) as response:
                                with open(filename, "wb") as f:
                                    while True:
                                        block = await response.content.read(1024)
                                        if not block:
                                            break
                                        f.write(block)

                            with open(filename, "rb") as f:
                                await ctx.send(file=discord.File(f))

                            os.remove(filename)
                else:
                    # send as embeds
                    for medianode in medias:
                        if medianode.get("is_video"):
                            await ctx.send(embed=content)
                            await ctx.send(medianode.get("video_url"))
                        else:
                            content.set_image(url=medianode.get("display_url"))
                            await ctx.send(embed=content)
                        content.description = None
                        content._author = None

        try:
            # delete discord automatic embed
            await ctx.message.edit(suppress=True)
        except discord.Forbidden:
            pass

    @flags.add_flag("urls", nargs="+")
    @flags.add_flag("-d", "--download", action="store_true")
    @flags.command(aliases=["twt"])
    async def twitter(self, ctx, **options):
        """Get all the images from one or more tweets."""
        for tweet_url in options["urls"]:
            if "status" in tweet_url:
                tweet_id = re.search(r"status/(\d+)", tweet_url).group(1)
            else:
                tweet_id = tweet_url

            try:
                tweet = await ctx.bot.loop.run_in_executor(
                    None,
                    lambda: self.twitter_api.get_status(
                        tweet_id, tweet_mode="extended"
                    ),
                )

            except Exception:
                await ctx.send(f":warning: Could not get tweet `{tweet_url}`")
                continue

            media_files = []
            try:
                media = tweet.extended_entities.get("media", [])
            except AttributeError:
                media = []

            if not media:
                await ctx.send(
                    f":warning: Could not find any images from tweet id `{tweet_id}`"
                )
                continue

            hashtags = []
            for hashtag in tweet.entities.get("hashtags", []):
                hashtags.append(f"#{hashtag['text']}")

            for i in range(len(media)):
                media_url = media[i]["media_url"]
                video_url = None
                if not media[i]["type"] == "photo":
                    video_urls = media[i]["video_info"]["variants"]
                    largest_rate = -1
                    for x in range(len(video_urls)):
                        if video_urls[x]["content_type"] == "video/mp4":
                            if video_urls[x]["bitrate"] > largest_rate:
                                largest_rate = video_urls[x]["bitrate"]
                                video_url = video_urls[x]["url"]
                                media_url = video_urls[x]["url"]
                media_files.append((" ".join(hashtags), media_url, video_url))

            content = discord.Embed(colour=int(tweet.user.profile_link_color, 16))
            content.set_author(
                icon_url=tweet.user.profile_image_url,
                name=f"@{tweet.user.screen_name}\n{media_files[0][0]}",
                url=f"https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}",
            )

            if options["download"]:
                # download file and rename, upload to discord
                async with aiohttp.ClientSession() as session:
                    await ctx.send(f"<{tweet.full_text.split(' ')[-1]}>")
                    timestamp = arrow.get(tweet.created_at).format("YYMMDD")
                    for n, file in enumerate(media_files, start=1):
                        # is image not video
                        if file[2] is None:
                            extension = "jpeg"
                        else:
                            extension = "mp4"

                        filename = f"{timestamp}-@{tweet.user.screen_name}-{tweet.id}-{n}.{extension}"
                        url = file[1].replace(".jpg", "?format=jpg&name=orig")
                        async with session.get(url) as response:
                            with open(filename, "wb") as f:
                                while True:
                                    block = await response.content.read(1024)
                                    if not block:
                                        break
                                    f.write(block)

                        with open(filename, "rb") as f:
                            await ctx.send(file=discord.File(f))

                        os.remove(filename)

            else:
                # just send link in embed
                for file in media_files:
                    url = file[1].replace(".jpg", "?format=jpg&name=orig")
                    content.set_image(url=url)
                    await ctx.send(embed=content)

                    if file[2] is not None:
                        # contains a video/gif, send it separately
                        await ctx.send(file[2])

                    content._author = None

        try:
            # delete discord automatic embed
            await ctx.message.edit(suppress=True)
        except discord.Forbidden:
            pass

    @commands.command(aliases=["gif", "gfy"])
    async def gfycat(self, ctx, *, query):
        """Search for a random gif."""

        scripts = []
        async with aiohttp.ClientSession() as session:
            tasks = []
            if len(query.split(" ")) == 1:
                tasks.append(
                    extract_scripts(session, f"https://gfycat.com/gifs/tag/{query}")
                )

            tasks.append(
                extract_scripts(session, f"https://gfycat.com/gifs/search/{query}")
            )
            scripts = sum(await asyncio.gather(*tasks), [])

        urls = []
        for script in scripts:
            try:
                data = json.loads(script.contents[0])
                for x in data["itemListElement"]:
                    if "url" in x:
                        urls.append(x["url"])
            except json.JSONDecodeError:
                continue

        if not urls:
            return await ctx.send("Found nothing!")

        msg = await ctx.send(f"**{query}** {random.choice(urls)}")

        async def randomize():
            await msg.edit(content=f"**{query}** {random.choice(urls)}")

        async def done():
            return True

        buttons = {"❌": msg.delete, "🔁": randomize, "🔒": done}
        asyncio.ensure_future(
            util.reaction_buttons(ctx, msg, buttons, only_author=True)
        )

    @commands.command()
    async def melon(self, ctx, timeframe):
        """Melon music charts."""
        if timeframe not in ["day", "month"]:
            if timeframe == "realtime":
                timeframe = ""
            elif timeframe == "rising":
                timeframe = "rise"
            else:
                raise exceptions.Info(
                    "Available timeframes: `[ day | month | realtime | rising ]`"
                )

        url = f"https://www.melon.com/chart/{timeframe}/index.htm"
        async with aiohttp.ClientSession() as session:
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:65.0) Gecko/20100101 Firefox/65.0",
            }
            async with session.get(url, headers=headers) as response:
                soup = BeautifulSoup(await response.text(), "html.parser")

        song_titles = [
            util.escape_md(x.find("span").find("a").text)
            for x in soup.find_all("div", {"class": "ellipsis rank01"})
        ]
        artists = [
            util.escape_md(x.find("a").text)
            for x in soup.find_all("div", {"class": "ellipsis rank02"})
        ]
        # albums = [
        #     util.escape_md(x.find("a").text)
        #     for x in soup.find_all("div", {"class": "ellipsis rank03"})
        # ]
        image = soup.find("img", {"onerror": "WEBPOCIMG.defaultAlbumImg(this);"}).get(
            "src"
        )

        content = discord.Embed(color=discord.Color.from_rgb(0, 205, 60))
        content.set_author(
            name=f"Melon top {len(song_titles)}"
            + ("" if timeframe == "" else f" - {timeframe.capitalize()}"),
            url=url,
            icon_url="https://i.imgur.com/hm9xzPz.png",
        )
        content.set_thumbnail(url=image)
        content.timestamp = ctx.message.created_at

        rows = []
        for i, (song, artist) in enumerate(zip(song_titles, artists), start=1):
            rows.append(f"`#{i:2}` **{artist}** — ***{song}***")

        await util.send_as_pages(ctx, content, rows)

    @commands.command()
    async def xkcd(self, ctx, comic_id=None):
        """Get a random xkcd comic"""
        if comic_id is None:
            async with aiohttp.ClientSession() as session:
                url = "https://c.xkcd.com/random/comic"
                headers = {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Connection": "keep-alive",
                    "Referer": "https://xkcd.com/",
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:66.0) Gecko/20100101 Firefox/66.0",
                }
                async with session.get(url, headers=headers) as response:
                    location = response.url
        else:
            location = f"https://xkcd.com/{comic_id}/"
        await ctx.send(location)

    @commands.command()
    async def google(self, ctx, *, query):
        """Search from google."""
        results = await self.google_client.search(query, safesearch=False)

        await util.paginate_list(
            ctx,
            [f"**{result.title}**\n{result.url}" for result in results],
            use_locking=True,
            only_author=True,
            index_entries=True,
        )

    @commands.command(aliases=["img"])
    async def googleimages(self, ctx, *, query):
        """Search from google images."""
        results = await self.google_client.search(
            query, safesearch=False, image_search=True
        )

        await util.paginate_list(
            ctx,
            [result.image_url for result in results],
            use_locking=True,
            only_author=True,
            index_entries=False,
        )


def setup(bot):
    bot.add_cog(Media(bot))


async def extract_scripts(session, url):
    async with session.get(url) as response:
        data = await response.text()
        soup = BeautifulSoup(data, "html.parser")
        return soup.find_all("script", {"type": "application/ld+json"})


class GGSoup:
    def __init__(self):
        self.soup = None

    async def create(self, region, summoner_name, sub_url=""):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://{region}.op.gg/summoner/{sub_url}userName={summoner_name}"
            ) as response:
                data = await response.text()
                self.soup = BeautifulSoup(data, "html.parser")

    def text(self, obj, classname, source=None):
        if source is None:
            source = self.soup
        a = source.find(obj, {"class": classname})
        return a.text.strip() if a else a

    def src(self, obj, classname, source=None):
        if source is None:
            source = self.soup
        a = source.find(obj, {"class": classname})
        return "https:" + a.get("src") if a else a
