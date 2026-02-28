#!/usr/bin/env python

"""
Sushi Chef for Touchable Earth: http://www.touchableearth.org/
Consists of videos and images.
Supports multiple languages -- just create another subclass of TouchableEarthChef!
"""

import os
import re
import requests
import tempfile
import time
import urllib
from urllib.parse import urlparse, parse_qs

from bs4 import BeautifulSoup
import pycountry
import youtube_dl
import moviepy.editor as mpe

from le_utils.constants import content_kinds, file_formats, languages
from ricecooker.chefs import SushiChef
from ricecooker.classes import nodes, files, licenses
from ricecooker.utils.caching import CacheForeverHeuristic, FileCache, CacheControlAdapter, InvalidatingCacheControlAdapter
from ricecooker.utils.browser import preview_in_browser
from ricecooker.utils.html import download_file
from ricecooker.utils.zip import create_predictable_zip
from ricecooker import config

LANG = "fr"

class VideoError(Exception):
    pass

sess = requests.Session()
cache = FileCache('.webcache')
forever_adapter = CacheControlAdapter(heuristic=CacheForeverHeuristic(), cache=cache)
ydl = youtube_dl.YoutubeDL({
    'quiet': True,
    'no_warnings': True,
    'writesubtitles': True,
    'allsubtitles': True,
})

sess.mount('http://www.touchableearth.org', forever_adapter)
sess.mount('https://i.ytimg.com', forever_adapter)

TE_LICENSE = licenses.SpecialPermissionsLicense(
    description="Permission has been granted by Touchable Earth to"
    " distribute this content through Kolibri.",
    copyright_holder="Touchable Earth Foundation (New Zealand)"
)


class TouchableEarthChef(SushiChef):
    """
    The chef class that takes care of uploading channel to the content curation server.

    We'll call its `main()` method from the command line script.
    """

    def get_channel(self, **kwargs):
        """
        Return the `ChannelNode` for the Touchable Earth for a particular langage.
        """
        if 'lang' not in kwargs:
            if LANG:
                lang = LANG
            else:
                raise ValueError('Must specify lang=?? on the command line. Supported languages are en, fr, ?????.')
        else:
            lang = kwargs['lang']

        # -fr is already taken, so we special-case that here.
        if lang=='fr':
            source_lang = 'french'
        else:
            source_lang = lang
        channel = nodes.ChannelNode(
            source_domain = 'www.touchableearth.org',
            source_id = 'touchable-earth-%s' % source_lang,
            title = 'Touchable Earth (%s)' % lang,
            thumbnail = 'https://d1iiooxwdowqwr.cloudfront.net/pub/appsubmissions/20140218003206_PROFILEPHOTO.jpg',
            description = 'Where kids teach kids about the world. Taught entirely by school age children in short videos, Touchable Earth promotes tolerance for gender, culture, and identity.',
            language = lang,
        )
        return channel

    def construct_channel(self, **kwargs):
        """
        Create ChannelNode and build topic tree.
        """
        channel = self.get_channel(**kwargs)
        add_countries_to_channel(channel, channel.language)
        return channel


def add_countries_to_channel(channel, language):
    doc = get_parsed_html_from_url("http://www.touchableearth.org/places/")
    places = doc.select("div.places-row a.custom-link")

    for place in places:
        title = place.text.strip()
        href = place["href"]
        url = "%s?lang=%s" % (href, language)
        channel.add_child(scrape_country(title, url, language))

def scrape_country(title, country_url, language):
    """
    title: China
    country_url: http://www.touchableearth.org/china-facts-welcome/?lang=fr
    """
    print("Scraping country node: %s (%s)" % (title, country_url))

    doc = get_parsed_html_from_url(country_url)
    country = doc.select_one(".breadcrumbs .taxonomy.category")
    href = country["href"]
    title = country.text.strip()

    topic = nodes.TopicNode(
        source_id=href,
        title=title,
        thumbnail='topic_thumbnail.png',
    )
    add_topics_to_country(doc, topic, language)
    return topic


def add_topics_to_country(doc, country_node, language):
    """
    country_url: http://www.touchableearth.org/china/
    """
    topic_options = doc.select(".sub_cat_dropdown .select_option_subcat option")
    topic_urls_added = set()

    for _, option in enumerate(topic_options):
        if option.has_attr("selected"):
            continue

        url = option["value"]
        title = option.text.strip()

        # Skip duplicates
        if url in topic_urls_added:
            continue
        else:
            topic_urls_added.add(url)

        category_node = scrape_category(title, url, language, country_node.title)
        if category_node:
            country_node.add_child(category_node)


def scrape_category(category_title, category_url, language, country_title):
    """
    category_title: Culture
    category_url: http://www.touchableearth.org/china/culture/
        ... redirects to: http://www.touchableearth.org/china-culture-boys-clothing/
    """
    print("  Scraping category node: %s (%s)" % (category_title, category_url))

    category_node = nodes.TopicNode(
        source_id=category_url,
        title=add_country_to_category(category_title, country_title),
        thumbnail='topic_thumbnail.png',
    )

    # Iterate over each item in the "subway" sidebar menu on the left.
    doc = get_parsed_html_from_url(category_url)
    if not doc:
        return None

    content_items = doc.select(".post_title_sub .current_post")
    slugs_added = set()

    for content in content_items:
        slug = content.select_one(".get_post_title")["value"]

        # Skip duplicates ... seems like the Touchable Earth website has them!
        if slug in slugs_added:
            continue
        else:
            slugs_added.add(slug)

        title = content.select_one(".get_post_title2")["value"]
        site_url = content.select_one(".site_url")["value"]
        url = "%s/%s?lang=%s" % (site_url, slug, language)
        content_node = scrape_content(title, url)
        if content_node:
            category_node.add_child(content_node)

    return category_node


def add_country_to_category(category_title, country_title):
    """E.g. "Facts" --> "Facts about India"."""
    title_formatter = {
        "facts": "Facts about %s",
        "family": "Family in %s",
        "culture": "Culture in %s",
        "friends": "Friends in %s",
        "play": "Playing in %s",
        "school": "School in %s",
    }.get(category_title.lower())

    if title_formatter:
        return title_formatter % country_title
    else:
        return "%s (%s)" % (category_title, country_title)


WATERMARK_SETTINGS = {
    "image": "watermark.png",
    "height": 68,
    "right": 16,
    "bottom": 16,
    "position": ("right", "bottom"),
    "with_overlay": True,
}

# TODO(davidhu): Move this function to Ricecooker to be reuseable. This also
# uses a lot of Ricecooker abstractions, so it'd also be better there for
# encapsulation.
def overlay_and_watermark_video(filename, youtube_id):
    # Check if we've processed this file before -- is it in the cache?
    key = files.generate_key("WATERMARKED", filename, settings=WATERMARK_SETTINGS)
    if not config.UPDATE and files.FILECACHE.get(key):
        return files.FILECACHE.get(key).decode('utf-8')

    # Create a temporary filename to write the watermarked video.
    tempf = tempfile.NamedTemporaryFile(
            suffix=".{}".format(file_formats.MP4), delete=False)
    tempf.close()
    tempfile_name = tempf.name

    # Now watermark it with the Touchable Earth logo!
    print("\t--- Watermarking and adding overlay ", filename)

    # First add the overlay image -- this is the image shown as the first frame
    # so that when the video hasn't been played yet, it will show this image
    # rather than a black screen (since Touchable Earth's videos start from
    # a blank black screen).

    # Download the overlay image based on the YouTube ID
    overlay_src = 'https://i.ytimg.com/vi_webp/%s/maxresdefault.webp' % youtube_id
    print("\t    ... grabbing overlay image from %s" % overlay_src)
    destination = tempfile.mkdtemp()
    overlay_filename = "overlay.webp"
    overlay_file = os.path.join(destination, overlay_filename)
    _, response = download_file(overlay_src, destination, request_fn=sess.get,
            filename=overlay_filename)

    video_clip = mpe.VideoFileClip(config.get_storage_path(filename), audio=True)

    if response.status_code == 200:
        overlay_clip = mpe.ImageClip(overlay_file).set_duration(0.1)
        concat_clips = mpe.concatenate_videoclips([overlay_clip, video_clip])
    else:
        concat_clips = mpe.concatenate_videoclips([video_clip])
        print("\t    WARNING: Could not download overlay image file from %s" % overlay_src)

    # Now create the watermark logo as a clip ...
    logo = (mpe.ImageClip(WATERMARK_SETTINGS["image"])
                .set_duration(concat_clips.duration)
                .resize(height=WATERMARK_SETTINGS["height"])
                .margin(right=WATERMARK_SETTINGS["right"],
                    bottom=WATERMARK_SETTINGS["bottom"], opacity=0)
                .set_pos(WATERMARK_SETTINGS["position"]))

    # And then combine it with the video clip.
    composite = mpe.CompositeVideoClip([concat_clips, logo])
    composite.duration = concat_clips.duration
    try:
        composite.write_videofile(tempfile_name, threads=4, audio_codec="aac")
    except Exception as e:
        raise VideoError(str(e))
    
    # Now move the watermarked file to Ricecooker storage and hash its name
    # so it can be validated.
    watermarked_filename = "{}.{}".format(
        files.get_hash(tempfile_name), file_formats.MP4)
    files.copy_file_to_storage(watermarked_filename, tempfile_name)
    os.unlink(tempfile_name)
    os.unlink(overlay_file)

    files.FILECACHE.set(key, bytes(watermarked_filename, "utf-8"))
    return watermarked_filename


class WatermarkedYouTubeVideoFile(files.YouTubeVideoFile):
    """A subclass of YouTubeVideoFile that watermarks and adds an initial
    overlay image to the video in a post-process step.
    """
    def __init__(self, youtube_id, **kwargs):
        self.youtube_id = youtube_id
        super(WatermarkedYouTubeVideoFile, self).__init__(youtube_id, **kwargs)

    def process_file(self):
        filename = super(WatermarkedYouTubeVideoFile, self).process_file()
        if filename is None:
            print ("\t\tERROR: Didn't get video")
            self.error = "Didn't get video"
            config.FAILED_FILES.append(self)
            return
        try:
            self.filename = overlay_and_watermark_video(filename, self.youtube_id)
        except VideoError:
            print ("\t\tERROR: Didn't get video (overlay step)")
            self.error = "Didn't get video (overlay step)"
            config.FAILED_FILES.append(self)
            return

        print("\t--- Watermarked ", self.filename)
        return self.filename


def scrape_content(title, content_url):
    """
    title: Boys' clothing
    content_url: http://www.touchableearth.org/china-culture-boys-clothing/
    """
    print("    Scraping content node: %s (%s)" % (title, content_url))

    doc = get_parsed_html_from_url(content_url)
    if not doc:  # 404
        return None

    description = create_description(doc)
    source_id = doc.select_one(".current_post.active .post_id")["value"]

    base_node_attributes = {
        "source_id": source_id,
        "title": title,
        "license": TE_LICENSE,
        "description": description,
    }

    youtube_iframe = doc.select_one(".video-container iframe")
    if youtube_iframe:
        youtube_url = doc.select_one(".video-container iframe")["src"]
        youtube_id = get_youtube_id_from_url(youtube_url)

        if not youtube_id:
            print("    *** WARNING: youtube_id not found for content url", content_url)
            print("    Skipping.")
            return None

        try:
            info = ydl.extract_info(youtube_url, download=False)
            subtitles = info.get("subtitles")
            subtitle_languages = subtitles.keys() if subtitles else []
            print ("      ... with subtitles in languages:", subtitle_languages)
        except youtube_dl.DownloadError as e:
            # Some of the videos have been removed from the YouTube channel --
            # skip creating content nodes for them entirely so they don't show up
            # as non-loadable videos in Kolibri.
            print("        NOTE: Skipping video download due to error: ", e)
            return None

        video_node = nodes.VideoNode(
            **base_node_attributes,
            derive_thumbnail=True,
            files=[WatermarkedYouTubeVideoFile(youtube_id=youtube_id)],
        )

        # Add subtitles in whichever languages are available.
        for language in subtitle_languages:
            video_node.add_file(files.YouTubeSubtitleFile(
                youtube_id=youtube_id, language=language))

        return video_node

    img = doc.select_one(".uncode-single-media-wrapper img")
    if img:
        img_src = img["data-guid"] or img["src"]
        destination = tempfile.mkdtemp()
        download_file(img_src, destination, request_fn=make_request, filename="image.jpg")

        with open(os.path.join(destination, "index.html"), "w") as f:
            f.write("""
                <!doctype html>
                <html>
                <head></head>
                <body>
                    <img src="image.jpg" style="width: 100%; max-width: 1200px;" />
                </body>
                </html>
            """)

        zip_path = create_predictable_zip(destination)

        return nodes.HTML5AppNode(
            **base_node_attributes,
            files=[files.HTMLZipFile(zip_path)],
            thumbnail=img_src,
        )

    return None


_STRIP_ENGLISH_RE = re.compile("English (About|More Info|Transcript):.*", re.DOTALL)

def _strip_english(text):
    return _STRIP_ENGLISH_RE.sub('', text)


def create_description(doc):
    about = _strip_english(doc.select_one("#tab-about").text).strip()
    transcript = _strip_english(doc.select_one("#tab-transcript").text).strip()
    more_info = _strip_english(doc.select_one("#tab-more-info").text).strip()

    nav_tabs = doc.select_one(".tab-container .nav-tabs")
    tab_titles = [tab.text.strip() for tab in nav_tabs.children]

    description = about

    if transcript:
        description += "\n\n%s: %s" % (tab_titles[1].upper(), transcript)

    if more_info:
        description += "\n\n%s: %s" % (tab_titles[2].upper(), more_info)

    # Replace TE's unicode apostrophes that don't seem to show up in HTML with
    # the unicode "RIGHT SINGLE QUOTATION MARK".
    description = description.replace("\x92", "\u2019")

    return description


# From https://stackoverflow.com/a/7936523
def get_youtube_id_from_url(value):
    """
    Examples:
    - http://youtu.be/SA2iWivDJiE
    - http://www.youtube.com/watch?v=_oPAwA_Udwc&feature=feedu
    - http://www.youtube.com/embed/SA2iWivDJiE
    - http://www.youtube.com/v/SA2iWivDJiE?version=3&amp;hl=en_US
    """
    query = urlparse(value)
    if query.hostname == 'youtu.be':
        return query.path[1:]
    if query.hostname in ('www.youtube.com', 'youtube.com'):
        if query.path == '/watch':
            p = parse_qs(query.query)
            return p['v'][0]
        if query.path[:7] == '/embed/':
            return query.path.split('/')[2]
        if query.path[:3] == '/v/':
            return query.path.split('/')[2]
    # fail?
    return None


# This is taken and modified from https://github.com/fle-internal/sushi-chef-ck12/blob/cb0d538b6857f399271d0895967727f635e58ee0/chef.py#L85
# TODO(davidhu): Extract to a util library
def make_request(url, clear_cookies=True, timeout=60, *args, **kwargs):
    if clear_cookies:
        sess.cookies.clear()

    # resolve ".." and "." references in url path to ensure cloudfront doesn't barf
    purl = urlparse(url)
    newpath = urllib.parse.urljoin(purl.path + "/", ".").rstrip("/")
    url = purl._replace(path=newpath).geturl()

    retry_count = 0
    max_retries = 5
    while True:
        try:
            response = sess.get(url, timeout=timeout, *args, **kwargs)
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout) as e:
            retry_count += 1
            print("Error with connection ('{msg}'); about to perform retry {count} of {trymax}."
                  .format(msg=str(e), count=retry_count, trymax=max_retries))
            time.sleep(retry_count * 1)
            if retry_count >= max_retries:
                return Dummy404ResponseObject(url=url)

    if response.status_code != 200:
        print("NOT FOUND:", url)
        return None

    return response


def get_parsed_html_from_url(url, *args, **kwargs):
    request = make_request(url, *args, **kwargs)
    if not request:
        return None

    html = request.content
    return BeautifulSoup(html, "html.parser")


if __name__ == '__main__':
    """
    This code will run when the sushi chef is called from the command line.
    """
    print("----- Scraping Touchable Earth channel! -----\n\n")
    TouchableEarthChef().main()

