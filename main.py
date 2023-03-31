#!/usr/bin/env python3
import boto3
import sys
from kubernetes import client, config
import os
import logging
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger("ecr-image-cleanup")
hdlr = logging.StreamHandler()
# fhdlr = logging.FileHandler("myapp.log")
logger.addHandler(hdlr)
# logger.addHandler(fhdlr)
logger.setLevel(level=os.environ.get("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("ecr-image-cleanup")

# Set a standard Global Localization
UTC = pytz.UTC


def build_image_uri(image: dict, repository: dict) -> dict:
    logger.debug(image)
    logger.debug(
        "Only include actual container images not .sig files which are a different mediaType"
    )
    if (
        image["imageManifestMediaType"]
        == "application/vnd.docker.distribution.manifest.v2+json"
    ):
        if "imageTags" in image:
            image[
                "image_uri"
            ] = f"{repository['repository_uri']}:{image['imageTags'][0]}"
        else:
            image[
                "image_uri"
            ] = f"{repository['repository_uri']}@{image['imageDigest']}"
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
    client: boto3.client, registry_id: str, repositories: list
) -> list:  # pragma: no cover
    """
    :param client boto3.client:
    :param repositories list:
    :return images list: returns a list of images located in a registry
    """
    logging.debug("Attempting to retrieve a list of images in ECR")
    images = []
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
                break
            images = append_image(images, imageDetails, repository)

    logger.debug(f"{images=}")
    return images


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
        is_image_referenced(image, k8s_images)
        or is_image_pulled_recently(image)
        or is_image_tagged_keep(image)
    ):
        logger.debug(f'{image["image_uri"]} is not deletable')
        return False
    else:
        logger.debug(f'{image["image_uri"]} is deletable')
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
    config.load_kube_config()

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
    ecr_images = get_ecr_images(client, registry_id, repositories)
    k8s_images = get_images_from_workloads()
    for image in ecr_images:
        logger.debug(f"{image=}")
        if is_image_deletable(image, k8s_images):
            deletable_images.append(image)
        else:
            keepable_images.append(image["image_uri"])

    logger.debug(f"{keepable_images=}")
    logger.debug(f"{deletable_images=}")
    for image in deletable_images:
        delete_image(client, image)


if __name__ == "__main__":  # pragma: no cover
    main()
