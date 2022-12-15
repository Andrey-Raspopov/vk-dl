import logging
import os
import shutil
import time
from datetime import datetime

import cv2
import numpy as np
import requests
import eventlet as eventlet

token = ''
output = open('out.md', 'w')


def get_data(domain):
    """Trying to request data from VK using vk_api
    Returns:
        List of N posts from vk.com/xxx, where
            N = config.reqCount
            xxx = config.vkDomain
    """
    timeout = eventlet.Timeout(20)
    try:
        data = requests.get(
            "https://api.vk.com/method/wall.get",
            params={
                "access_token": token,
                "v": 5.126,
                "domain": domain
            },
        )
        return data.json()["response"]["items"]
    except eventlet.timeout.Timeout:
        # addLog("w", "Got Timeout while retrieving VK JSON data. Cancelling...")
        return None
    finally:
        timeout.cancel()


def parse_posts(items):
    for item in items:
        output.write(f'#{item["id"]}\n')
        if item["marked_as_ads"] == 1:
            add_log(
                "i",
                f"[id:{item['id']}]Post was skipped because it was flagged as ad",
            )
            continue
        add_log("i", f"[id:{item['id']}] Bot is working with this post")

        def get_link(attachment):
            link_object = attachment["link"]["url"]

            if link_object not in text_of_post:
                return link_object

        def get_video(attachment):
            def get_video_url(owner_id, video_id, access_key):
                data = requests.get(
                    'https://api.vk.com/method/video.get',
                    params={
                        "access_token": token,
                        "v": 5.126,
                        'videos': f'{owner_id}_{video_id}_{access_key}'
                    }
                )
                return None
                # TODO: check access
                return data.json()["response"]["items"][0]["files"]["external"]

            video = get_video_url(
                attachment["video"]["owner_id"],
                attachment["video"]["id"],
                attachment["video"]["access_key"],
            )
            time.sleep(2)
            if video is not None:
                return video
            else:
                return f"https://vk.com/video{attachment['video']['owner_id']}_{attachment['video']['id']}"

        def get_photo(attachment):
            photo = attachment["photo"]["sizes"]
            if photo[-1]["type"] == "z":
                for url in photo:
                    if url["type"] == "w":
                        return url["url"]
                    elif url["type"] == "z":
                        return url["url"]
            elif photo[-1]["type"] != "z":
                return photo[-1]["url"]

        def get_doc(attachment):
            doc_url = attachment["doc"]["url"]
            return doc_url

        def parse_attachments(post, linklist, videos, photos, documents):
            for attachment in post["attachments"]:
                if attachment["type"] == "link":
                    linklist.append(get_link(attachment))
                elif attachment["type"] == "video":
                    temp_vid = get_video(attachment)
                    if temp_vid is not None:
                        videos.append(temp_vid)
                elif attachment["type"] == "photo":
                    photos.append(get_photo(attachment))
                elif attachment["type"] == "doc":
                    if attachment["doc"]["ext"] != "gif":
                        documents.append(get_doc(attachment))

        text_of_post = item["text"]
        links_list = []
        videos_list = []
        photo_url_list = []
        docs_list = []
        gif_link = ""

        if "attachments" in item:
            parse_attachments(
                item, links_list, videos_list, photo_url_list, docs_list
            )
        text_of_post = compile_links_and_text(
            item["id"], text_of_post, links_list, videos_list, "post"
        )
        if "copy_history" in item and text_of_post != "":
            text_of_post = f"""{text_of_post}\n\nREPOST ↓"""
        send_posts(
            item["id"], text_of_post, photo_url_list, docs_list, gif_link, "post"
        )
        # cleaning("after")

        if "copy_history" in item:
            # cleaning("before")

            item_repost = item["copy_history"][0]
            link_to_reposted_post = (
                f"https://vk.com/wall{item_repost['from_id']}_{item_repost['id']}"
            )
            text_of_post_rep = item_repost["text"]
            links_list_rep = []
            videos_list_rep = []
            photo_url_list_rep = []
            docs_list_rep = []
            gif_link_rep = ""

            if "attachments" in item_repost:
                parse_attachments(
                    item_repost,
                    links_list_rep,
                    videos_list_rep,
                    photo_url_list_rep,
                    docs_list_rep,
                )
            text_of_post_rep = compile_links_and_text(
                item["id"],
                text_of_post_rep,
                links_list_rep,
                videos_list_rep,
                "repost",
                link_to_reposted_post,
            )
            send_posts(
                item["id"],
                text_of_post_rep,
                photo_url_list_rep,
                docs_list_rep,
                gif_link_rep,
                "repost",
            )
            # cleaning("after")


def compile_links_and_text(post_id, text_of_post, links_list, videos_list, *repost):
    first_link = True

    def add_video():
        nonlocal first_link
        nonlocal text_of_post
        if videos_list != [] and videos_list != [None]:
            for video in videos_list:
                if video not in text_of_post:
                    if first_link:
                        text_of_post += f"\n\n{video}"
                        first_link = False
                    elif not first_link:
                        text_of_post += f"\n{video}"
            add_log(
                "i",
                f"[id:{post_id}] Link(s) to video(s) was(were) added to post text",
            )

    def add_link():
        nonlocal first_link
        nonlocal text_of_post
        if links_list != [] and links_list != [None]:
            for link in links_list:
                if link not in text_of_post:
                    if first_link:
                        text_of_post += f"\n\n[{link}]({link})"
                        first_link = False
                    elif not first_link:
                        text_of_post += f"\n[{link}]({link})"
            add_log("i", f"[id:{post_id}] Link(s) was(were) added to post text")

    add_video()
    add_link()
    if repost[0] == "repost":
        text_of_post = f'<a href="{repost[1]}"><b>REPOST ↓</b></a>\n\n<i>{text_of_post}</i>'
    return text_of_post


def cleaning(when):
    try:
        if when == "before":
            if "temp" in os.listdir():
                shutil.rmtree("temp")
                os.mkdir("temp")
            elif "temp" not in os.listdir():
                os.mkdir("temp")
        elif when == "after":
            shutil.rmtree("temp")
    except Exception as ex:
        add_log(
            "e", f"Something [{type(ex).__name__}] went wrong in cleaning(): {str(ex)}"
        )


def add_log(log_type, text):
    if log_type == "w":
        log_message = f"[WARNING] {text}"
        print(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "| " + log_message)
        logging.warning(log_message)
    elif log_type == "i":
        log_message = f"[Bot] [Info] {text}"
        print(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "| " + log_message)
        logging.info(log_message)
    elif log_type == "e":
        log_message = f"[ERROR] {text}"
        print(datetime.now().strftime("%d-%m-%Y %H:%M:%S"), "| " + log_message)
        logging.error(log_message)


def send_posts(post_id, text_of_post, photo_url_list, docs_list, *repost):
    def start_sending():
        if len(photo_url_list) == 0:
            add_log("i", f"[id:{post_id}] Bot is trying to send text post")
            if repost[0] == "post":
                send_text_post("post")
            elif repost[0] == "repost":
                send_text_post("repost")
        elif len(photo_url_list) == 1:
            add_log("i", f"[id:{post_id}] Bot is trying to send post with photo")
            send_photo_post()
        elif len(photo_url_list) >= 2:
            add_log("i", f"[id:{post_id}] Bot is trying to send post with photos")
            send_photos_post()

        if docs_list:
            send_docs()

    def send_text_post(type_of_post):
        if type_of_post == "post":
            output.write(text_of_post)
        elif type_of_post == "repost":
            output.write(
                text_of_post
            )
        add_log("i", f"[id:{post_id}] Text post sent")

    def send_photo_post():
        response = requests.get(photo_url_list[0]).content
        nparr = np.fromstring(response, np.uint8)
        img_np = cv2.imdecode(nparr, flags=1)
        resized = cv2.resize(img_np, (200, 200))
        cv2.imwrite(f'images/{hash(photo_url_list[0])}.png', resized)
        output.write(f'![{hash(photo_url_list[0])}](images/{hash(photo_url_list[0])}.png)\n')
        output.write(f'{text_of_post}\n')
        add_log("i", f"[id:{post_id}] Text post with photo sent")

    def send_photos_post():
        output.write(f'\n{text_of_post}\n')
        for urlPhoto in photo_url_list:
            response = requests.get(urlPhoto).content
            nparr = np.fromstring(response, np.uint8)
            img_np = cv2.imdecode(nparr, flags=1)
            resized = cv2.resize(img_np, (200, 200))
            cv2.imwrite(f'images/{hash(photo_url_list[0])}.png', resized)
            output.write(f'![{hash(urlPhoto)}](images/{hash(urlPhoto)}.png)')

        output.write('\n')

        add_log("i", f"[id:{post_id}] Text post with photos sent")

    def send_docs():
        def send_doc(document):
            output.write(document)
            add_log("i", f"[id:{post_id}] Document sent")

        for doc in docs_list:
            send_doc(doc)

    start_sending()


communities = []

posts = get_data(communities[0])
parse_posts(posts)
output.close()
