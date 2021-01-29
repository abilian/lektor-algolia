from typing import Any, Dict, List, Set

from algoliasearch.exceptions import AlgoliaException
from algoliasearch.search_client import SearchClient
from algoliasearch.search_index import SearchIndex
from lektor.db import Record
from lektor.pluginsystem import Plugin
from lektor.project import Project
from lektor.publisher import Publisher, PublishError
from lektor.types.formats import Markdown


class AlgoliaPlugin(Plugin):
    name = "algolia"
    description = (
        "Adds Algolia as a deploy target. Use algolia://<index> to deploy to an index."
    )

    def on_setup_env(self, **extra):
        config = self.get_config()
        self.env.algolia_credentials = {}
        self.env.algolia_credentials["app_id"] = config.get("app_id")
        self.env.algolia_credentials["api_key"] = config.get("api_key")
        self.env.publishers["algolia"] = AlgoliaPublisher


class AlgoliaPublisher(Publisher):
    algolia: SearchClient

    def get_index(self, index_name, credentials) -> SearchIndex:
        merged_creds = merge_credentials(self.env.algolia_credentials, credentials)

        # yield "Checking for Algolia credentials and index..."
        if "app_id" not in merged_creds or "api_key" not in merged_creds:
            raise PublishError(
                "Could not connect to Algolia. "
                + "Make sure api_key and app_id are present in your configs/algolia.ini file."
            )

        app_id = merged_creds["app_id"]
        api_key = merged_creds["api_key"]
        self.algolia = SearchClient.create(app_id, api_key)

        try:
            index = self.algolia.init_index(index_name)
        except AlgoliaException as exc:
            raise PublishError(
                f'Algolia index "{index_name}" does not exist, '
                f"or the API key provided does not have access to it. "
                f"Please create the index / verify your credentials on their website."
            ) from exc

        return index

    def publish(self, target_url, credentials=None, **extra):
        index_name = target_url.netloc
        index = self.get_index(index_name, credentials)

        local = list_local()
        local_keys = {record["objectID"] for record in local}
        yield "Found %d local records to index." % len(local)

        remote_keys = list_remote_keys(index)
        yield "Found %d existing remote records in the index." % len(remote_keys)

        yield "Computing diff for index update..."
        keys_to_delete: List[str] = list(set(remote_keys) - set(local_keys))
        res_delete = index.delete_objects(keys_to_delete)
        delete_count = len(res_delete.raw_responses)
        yield f"Deleted {delete_count} stale records from remote index."

        res_add = index.save_objects(local)
        add_count = len(res_add.raw_responses)
        yield f"Finished submitting {add_count} new/updated records to the index."
        yield (
            "Processing the updated index is asynchronous, so Aloglia may take a "
            "while to reflect the changes."
        )

        self.algolia.close()


def list_remote_keys(index: SearchIndex) -> List[str]:
    """handle pagination eventually..."""
    all_object_ids: Set[str] = set()
    params = {"attributesToRetrieve": "objectID", "hitsPerPage": 100}
    first_page = index.search("", params)
    first_page_hits = hit_object_ids(first_page)
    all_object_ids.update(first_page_hits)

    page_count = first_page["nbPages"]
    for i in range(1, page_count):
        next_page = index.search("", dict(params, page=i))
        if next_page["nbHits"] <= 0:
            break
        next_page_hits = hit_object_ids(next_page["hits"])
        all_object_ids.update(next_page_hits)

    return list(all_object_ids)


def list_local() -> List[Dict[str, Any]]:
    project = Project.discover()
    env = project.make_env()
    pad = env.new_pad()
    root = pad.root
    return get_all_records(pad, root)


def get_all_records(pad, record) -> List[Dict[str, Any]]:
    records = []
    for child in record.children.all():
        if is_indexable(child):
            model = child.datamodel
            model_json = model.to_json(pad, child)
            model_field_names = public_field_names(model_json["fields"])
            child_data = {
                field_name: stringify(child, field_name)
                for field_name in model_field_names
            }
            child_data["objectID"] = child["_gid"]
            # upload path so we can send the user to the right url for a search query!
            child_data["_path"] = child["_path"]
            records.append(child_data)
        records += get_all_records(pad, child)
    return records


def public_field_names(model_fields):
    def is_public_field(field):
        # ignore system fields and the indexed boolean
        name = field["name"]
        return name[0] != "_" and name != "indexed"

    return [field["name"] for field in model_fields if is_public_field(field)]


def stringify(record, field_name):
    val = record[field_name]
    if isinstance(val, Markdown):
        return val.source
    return str(val)


def hit_object_ids(search_page: Dict[str, Any]) -> Set[str]:
    return {hit["objectID"] for hit in search_page["hits"]}


def is_indexable(record: Record) -> bool:
    return True
    # debug(record._data)
    # return "indexed" in record and record["indexed"] == True


def merge_credentials(config_creds, cli_creds):
    """merge config file credentials with command line credentials."""
    merged_creds = config_creds
    # do this second to prefer cli creds over config file
    if cli_creds:
        if cli_creds["username"]:
            merged_creds["app_id"] = cli_creds["username"]
        if cli_creds["password"]:
            merged_creds["api_key"] = cli_creds["password"]
        if cli_creds["key"]:
            merged_creds["api_key"] = cli_creds["key"]
    return merged_creds
