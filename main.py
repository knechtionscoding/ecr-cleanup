#!/usr/bin/env python3
import boto3
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

import pytz
from kubernetes import client, config

logger = logging.getLogger("ecr-image-cleanup")
hdlr = logging.StreamHandler()
# fhdlr = logging.FileHandler("myapp.log")
logger.addHandler(hdlr)
# logger.addHandler(fhdlr)
logger.setLevel(level=os.environ.get("LOG_LEVEL", "INFO").upper())

# Set a standard Global Localization
UTC = pytz.UTC

CONTAINER_MANIFEST_MEDIA_TYPES = {
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
}

MANIFEST_LIST_MEDIA_TYPES = {
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.index.v1+json",
}

# These artifact media types represent standard image config blobs, not ancillary artifacts.
SAFE_ARTIFACT_MEDIA_TYPES = {
    None,
    "application/vnd.oci.image.config.v1+json",
    "application/vnd.docker.container.image.v1+json",
}


def is_container_manifest(image: dict) -> bool:
    """
    Determine whether the ECR entry is an actual runnable container manifest.
    Artifacts such as cosign signatures set artifactMediaType and should be skipped.
    """
    media_type = image.get("imageManifestMediaType")
    artifact_media_type = image.get("artifactMediaType")

    if media_type in MANIFEST_LIST_MEDIA_TYPES:
        return True

    if media_type in CONTAINER_MANIFEST_MEDIA_TYPES:
        if artifact_media_type in SAFE_ARTIFACT_MEDIA_TYPES:
            return True
        logger.debug(
            "Skipping artifact %s with unsupported artifact media type %s",
            image.get("imageDigest"),
            artifact_media_type,
        )
        return False

    logger.debug(
        "Skipping %s with unsupported manifest media type %s",
        image.get("imageDigest"),
        media_type,
    )
    return False


def extract_subject_digest(manifest_body: str) -> str | None:
    """
    Pull the OCI subject digest from an artifact manifest body if present.
    """
    try:
        manifest = json.loads(manifest_body)
    except json.JSONDecodeError:
        logger.warning("Unable to decode artifact manifest body")
        return None

    subject = manifest.get("subject")
    if isinstance(subject, dict):
        return subject.get("digest")
    return None


def get_artifact_subject_digest(
    client: boto3.client,
    registry_id: str,
    repository: dict,
    image: dict,
) -> str | None:
    """
    Retrieve the subject digest for an artifact manifest so we can associate it with its image.
    """
    media_type = image.get("imageManifestMediaType")
    if not media_type:
        return None

    try:
        response = client.batch_get_image(
            registryId=registry_id,
            repositoryName=repository["repository_name"],
            imageIds=[{"imageDigest": image["imageDigest"]}],
            acceptedMediaTypes=[media_type],
        )
    except client.exceptions.ImageNotFoundException:
        logger.warning("Artifact %s no longer exists", image.get("imageDigest"))
        return None

    images = response.get("images", [])
    if not images:
        logger.debug("No artifact data returned for %s", image.get("imageDigest"))
        return None

    manifest_body = images[0].get("imageManifest")
    if not manifest_body:
        logger.debug("Artifact manifest missing for %s", image.get("imageDigest"))
        return None

    subject_digest = extract_subject_digest(manifest_body)
    if not subject_digest:
        logger.debug(
            "Artifact %s manifest has no subject digest", image.get("imageDigest")
        )
    return subject_digest


def build_image_uri(image: dict, repository: dict) -> dict:
    logger.debug(image)
    logger.debug(
        "Only include actual container images not .sig files which are a different mediaType"
    )
    if is_container_manifest(image):
        if "imageTags" in image:
            image["image_uri"] = (
                f"{repository['repository_uri']}:{image['imageTags'][0]}"
            )
        else:
            image["image_uri"] = (
                f"{repository['repository_uri']}@{image['imageDigest']}"
            )
        return image
    else:
        return None


def append_image(images: list, imageDetails: list, repository: dict) -> list:
    for image in imageDetails:
        image = build_image_uri(image, repository)
        if image:
            images.append(image)

    return images


def get_images_from_workloads() -> list:  # pragma: no cover
    """
    Gets every single pod, deployment, cronjob, etc and gets the image from them.
    :return images list:
    """

    k8s_images = []

    def parse_images(workload: dict, images: list) -> list:
        # Throw away function that allows us to check for all images in a workload
        spec = workload.spec.template.spec
        if spec.init_containers:
            for container in spec.init_containers:
                image = container.image
                images.append(container.image)

        for container in spec.containers:
            image = container.image
            images.append(image)
        return images

    v1 = client.CoreV1Api()
    api = client.AppsV1Api()
    batch = client.BatchV1Api()

    logger.info("Getting Daemonsets from the K8s API")
    daemonset_list = api.list_daemon_set_for_all_namespaces(watch=False)
    for daemonset in daemonset_list.items:
        k8s_images = parse_images(daemonset, k8s_images)

    logger.info("Getting Deployments from the K8s API")
    deployment_list = api.list_deployment_for_all_namespaces(watch=False)
    for deployment in deployment_list.items:
        k8s_images = parse_images(deployment, k8s_images)

    logger.info("Getting Statefulset from the K8s API")
    statefulset_list = api.list_stateful_set_for_all_namespaces(watch=False)
    for statefulset in statefulset_list.items:
        k8s_images = parse_images(statefulset, k8s_images)

    logger.info("Getting Cronjobs from the K8s API")
    cronjob_list = batch.list_cron_job_for_all_namespaces(watch=False)
    for cronjob in cronjob_list.items:
        k8s_images = parse_images(cronjob.spec.job_template, k8s_images)

    logger.info("Getting Jobs from the K8s API")
    job_list = batch.list_job_for_all_namespaces(watch=False)
    for job in job_list.items:
        k8s_images = parse_images(job, k8s_images)

    logger.info("Getting Pods from the K8s API")
    pod_list = v1.list_pod_for_all_namespaces(watch=False)
    for pod in pod_list.items:
        spec = pod.spec
        if spec.init_containers:
            for container in spec.init_containers:
                k8s_images.append(container.image)

        for container in spec.containers:
            k8s_images.append(container.image)

    logger.debug("converting the list of images to a set to only give unique values")
    set_images = set(k8s_images)
    logger.debug("convert set back to list for return")
    unique_k8s_images = list(set_images)

    return unique_k8s_images


def get_ecr_repositories(
    client: boto3.client, registry: str
) -> list:  # pragma: no cover
    """
    :param client boto3.client:
    :param registry str:
    Gets a list of image repositories in a registry
    :return repositories list:
    """
    logging.debug("Attempting to retrieve a list of repositories in ECR")
    repositories = []
    paginator = client.get_paginator("describe_repositories")
    for response in paginator.paginate(registryId=registry):
        logger.debug(f"{response=}")
        for repository in response["repositories"]:
            logger.debug(f"{repository=}")

            tags = client.list_tags_for_resource(
                resourceArn=repository["repositoryArn"]
            )

            repo = {
                "repository_name": repository["repositoryName"],
                "repository_uri": repository["repositoryUri"],
            }

            for tag in tags["tags"]:
                if tag["Key"] == "Approved" and not bool(tag["Value"]):
                    logger.info("Images in repo should be deleted")
                    repo["delete"] = True

            repositories.append(repo)

    logger.debug(repositories)
    return repositories


def get_ecr_images(
    client: boto3.client, registry_id: str, repositories: list, minimum_image_age: int
) -> tuple[list, dict]:  # pragma: no cover
    """
    :param client boto3.client:
    :param repositories list:
    :return images list: returns a list of images located in a registry
    """
    logging.debug("Attempting to retrieve a list of images in ECR")
    images = []
    artifact_index = defaultdict(list)
    paginator = client.get_paginator("describe_images")
    for repository in repositories:
        for response in paginator.paginate(
            registryId=registry_id, repositoryName=repository["repository_name"]
        ):
            imageDetails = response["imageDetails"]
            logger.debug(imageDetails)
            if len(imageDetails) == 1:
                logger.info(
                    f"Image {repository['repository_uri']}@{imageDetails[0]['imageDigest']} is the only image in the repository skipping"
                )
                if "lastRecordedPullTime" in imageDetails:
                    last_pull_time = imageDetails["lastRecordedPullTime"]
                    localized_now_ts = UTC.localize(
                        datetime.now() - timedelta(minimum_image_age)
                    )
                    if last_pull_time > localized_now_ts:
                        logger.debug(
                            f"The last pulltime was more than {minimum_image_age} days ago. Skipping image."
                        )
                        logger.info(
                            f"Image {repository['repository_uri']}@{imageDetails[0]['imageDigest']} is the only image in the repository skipping and hasn't been pulled in 7 days, consider deleting"
                        )
                else:
                    logger.info(
                        f"Image {repository['repository_uri']}@{imageDetails[0]['imageDigest']} is the only image in the repository skipping and hasn't been pulled in 7 days, consider deleting"
                    )
                break
            for image in imageDetails:
                built_image = build_image_uri(image, repository)
                if built_image:
                    images.append(built_image)
                else:
                    subject_digest = get_artifact_subject_digest(
                        client, registry_id, repository, image
                    )
                    if subject_digest:
                        artifact_entry = image.copy()
                        artifact_entry["repository_uri"] = repository["repository_uri"]
                        artifact_entry["image_uri"] = (
                            f"{repository['repository_uri']}@{image['imageDigest']}"
                        )
                        artifact_entry["subjectDigest"] = subject_digest
                        artifact_index[subject_digest].append(artifact_entry)

    logger.debug(f"{images=}")
    return images, dict(artifact_index)


def is_image_pushed_recently(image: dict) -> bool:
    """
    :param image dict: image details
    Checks to see if the image has been pushed in the last 7 days
    :return bool: if the image has been pushed in the last 7 days True will be returned
    """
    logging.debug("Checking if the image has been pushed recently")
    logger.debug(f"{image=}")
    if "imagePushedAt" in image:
        last_pull_time = image["imagePushedAt"]
        localized_now_ts = UTC.localize(datetime.now() - timedelta(7))
        logger.debug(last_pull_time)
        logger.debug(localized_now_ts)
        if last_pull_time > localized_now_ts:
            logger.debug("The last pulltime was more than 7 days ago")
            return True
        else:
            return False
    else:
        logger.info(
            f"There is no imagePushedAt because the {image['image_uri']} has something terribly wrong with it"
        )
        return False


def is_image_pulled_recently(image: dict) -> bool:
    """
    :param image dict: image details
    Checks to see if the image has been pulled in the last 7 days
    :return bool: if the image has been pulled in the last 7 days True will be returned
    """
    logging.debug("Checking if the image has been pulled recently")
    logger.debug(f"{image=}")
    if "lastRecordedPullTime" in image:
        last_pull_time = image["lastRecordedPullTime"]
        localized_now_ts = UTC.localize(datetime.now() - timedelta(7))
        logger.debug(last_pull_time)
        logger.debug(localized_now_ts)
        if last_pull_time > localized_now_ts:
            logger.debug("The last pulltime was more than 7 days ago")
            return True
        else:
            return False
    else:
        logger.info(
            f"There is no lastRecordPullTime because the {image['image_uri']} has never been pulled or ECR has no record of it being pulled"
        )
        return False


def is_image_tagged_keep(image: dict) -> bool:
    """
    :param image dict: imgae response from ecr client

    Checks to see if the tag is the only one in the ecr repository.
    :return bool: if the tag of the image is keep then don't delete
    """
    if "imageTags" in image:
        logger.debug(f"{image['imageTags']=}")
        if "keep" in image["imageTags"]:
            logger.info(f"{image['image_uri']} was tagged keep")
            return True
        else:
            logger.info(f"{image['image_uri']} was not tagged keep")
            return False
    else:
        logger.debug(f"{image['image_uri']} has no tags configured")
        return False


def is_image_referenced(image: dict, images: list) -> bool:
    """
    :param image dict: full name of the image
    :param image list: list of images that k8s knows about/uses

    Checks to see if the image is referenced in any pods or pod creation controllers (i.e. deployments, cronjobs, statefulsets, jobs, daemonsets)
    :return bool: if the image is referenced in a workload object True will be returned.
    """
    if image["image_uri"] in images:
        logger.info(f"{image['image_uri']} was found in k8s workload")
        return True
    else:
        logger.info(f"{image['image_uri']} was not found in k8s workload")
        return False


def is_repository_approved(
    client: boto3.client, registry_id: str, repositories: dict, images: list
) -> list:
    paginator = client.get_paginator("describe_images")
    for repository in repositories:
        for response in paginator.paginate(
            registryId=registry_id, repositoryName=repository["repository_name"]
        ):
            imageDetails = response["imageDetails"]
            logger.debug(imageDetails)
            if "delete" in repository and repository["delete"]:
                logger.info("Repo is tagged for deletion")
                images = append_image(images, imageDetails, repository)
    return images


def is_image_deletable(image: dict, k8s_images: list) -> bool:
    """
    :param image dict: image details from aws

    Evaluates an image against a set of rules to determine if it should be deleted.

    :return bool: if the image should be deleted True will be returned
    """
    # TODO: Make it handle multiple tags

    if (
        is_image_pushed_recently(image)
        or is_image_referenced(image, k8s_images)
        or is_image_pulled_recently(image)
        or is_image_tagged_keep(image)
    ):
        logger.debug(f"{image['image_uri']} is not deletable")
        return False
    else:
        logger.debug(f"{image['image_uri']} is deletable")
        return True


def delete_image(client: boto3.client, image: dict):  # pragma: no cover
    """
    :param client boto3.client: configuration for boto3
    :param image dict: image response from ecr client

    Deletes an image from ECR
    """

    """
    ECR.Client.exceptions.ServerException

    ECR.Client.exceptions.InvalidParameterException

    ECR.Client.exceptions.RepositoryNotFoundException
    """
    logger.info(f"Deleting {image['image_uri']}")
    if os.getenv("DRY_RUN"):
        return True
    else:
        client.batch_delete_image(
            registryId=image["registryId"],
            repositoryName=image["repositoryName"],
            imageIds=[
                {"imageDigest": image["imageDigest"]},
            ],
        )


def main():  # pragma: no cover
    deletable_images = []
    keepable_images = []
    try:
        config.load_kube_config()
    except config.config_exception.ConfigException:
        config.load_incluster_config()

    minimum_image_age: int = int(os.getenv("MINIMUM_IMAGE_AGE", "7"))
    client = boto3.client("ecr")
    if os.getenv("AWS_REGISTRY_ID"):
        registry_id = os.getenv("AWS_REGISTRY_ID")
    else:
        try:
            registry_id = client.describe_registry()["registryId"]
        except client.exceptions.ValidationException:
            logger.error(
                "GOV Cloud Doesn't support describe registry. Please add the environment variable AWS_REGISTRY_ID instead."
            )
            sys.exit(1)
    repositories = get_ecr_repositories(client, registry_id)
    ecr_images, artifact_index = get_ecr_images(
        client, registry_id, repositories, minimum_image_age
    )
    k8s_images = get_images_from_workloads()
    for image in ecr_images:
        logger.debug(f"{image=}")
        if is_image_deletable(image, k8s_images):
            deletable_images.append(image)
            related_artifacts = artifact_index.get(image["imageDigest"], [])
            if related_artifacts:
                deletable_images.extend(related_artifacts)
        else:
            keepable_images.append(image["image_uri"])

    logger.debug(f"{keepable_images=}")
    logger.debug(f"{deletable_images=}")
    for image in deletable_images:
        delete_image(client, image)


if __name__ == "__main__":  # pragma: no cover
    main()
