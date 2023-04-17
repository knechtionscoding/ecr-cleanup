import main
import pytest
from datetime import datetime, timedelta
import pytz

UTC = pytz.UTC


@pytest.mark.parametrize(
    "image,repository,result",
    [
        (
            {
                "imageManifestMediaType": "application/vnd.docker.distribution.manifest.v2+json",
                "imageTags": ["test"],
            },
            {"repository_uri": "testing"},
            {
                "imageManifestMediaType": "application/vnd.docker.distribution.manifest.v2+json",
                "imageTags": ["test"],
                "image_uri": "testing:test",
            },
        ),
        (
            {
                "imageManifestMediaType": "application/vnd.docker.distribution.manifest.v2+json",
                "imageDigest": "digest",
            },
            {"repository_uri": "testing"},
            {
                "imageManifestMediaType": "application/vnd.docker.distribution.manifest.v2+json",
                "imageDigest": "digest",
                "image_uri": "testing@digest",
            },
        ),
        (
            {
                "imageManifestMediaType": "test",
                "imageTags": ["test"],
            },
            {"repository_uri": "testing"},
            None,
        ),
        (
            {
                "imageManifestMediaType": "application/vnd.oci.image.manifest.v1+json",
                "imageTags": ["test"],
            },
            {"repository_uri": "testing"},
            None,
        ),
    ],
)
def test_build_image_uri(image, repository, result):
    assert (main.build_image_uri(image, repository)) == result


@pytest.mark.parametrize(
    "image,imageDetails,repository,result",
    [
        (
            [],
            [
                {
                    "imageManifestMediaType": "application/vnd.docker.distribution.manifest.v2+json",
                    "imageTags": ["test"],
                }
            ],
            {"repository_uri": "testing"},
            [
                {
                    "imageManifestMediaType": "application/vnd.docker.distribution.manifest.v2+json",
                    "imageTags": ["test"],
                    "image_uri": "testing:test",
                }
            ],
        ),
        (
            [],
            [
                {
                    "imageManifestMediaType": "application/vnd.docker.distribution.manifest.v2+json",
                    "imageDigest": "digest",
                }
            ],
            {"repository_uri": "testing"},
            [
                {
                    "imageManifestMediaType": "application/vnd.docker.distribution.manifest.v2+json",
                    "imageDigest": "digest",
                    "image_uri": "testing@digest",
                }
            ],
        ),
        (
            [],
            [
                {
                    "imageManifestMediaType": "test",
                    "imageTags": ["test"],
                }
            ],
            {"repository_uri": "testing"},
            [],
        ),
        (
            [],
            [
                {
                    "imageManifestMediaType": "application/vnd.oci.image.manifest.v1+json",
                    "imageTags": ["test"],
                }
            ],
            {"repository_uri": "testing"},
            [],
        ),
    ],
)
def test_append_image(image, imageDetails, repository, result):
    assert (main.append_image(image, imageDetails, repository)) == result


@pytest.mark.parametrize(
    "image,result",
    [
        (
            {
                "lastRecordedPullTime": UTC.localize(datetime.now() - timedelta(2)),
            },
            True,
        ),
        (
            {
                "lastRecordedPullTime": UTC.localize(datetime.now() - timedelta(10)),
            },
            False,
        ),
        (
            {"image_uri": "test"},
            False,
        ),
    ],
)
def test_is_image_pulled_recently(image, result):
    assert (main.is_image_pulled_recently(image)) == result


@pytest.mark.parametrize(
    "image,result",
    [
        (
            {
                "imagePushedAt": UTC.localize(datetime.now() - timedelta(2)),
            },
            True,
        ),
        (
            {
                "imagePushedAt": UTC.localize(datetime.now() - timedelta(10)),
            },
            False,
        ),
        (
            {"image_uri": "test"},
            False,
        ),
    ],
)
def test_is_image_pushed_recently(image, result):
    assert (main.is_image_pushed_recently(image)) == result


@pytest.mark.parametrize(
    "image,result",
    [
        (
            {"imageTags": ["keep"], "image_uri": "test"},
            True,
        ),
        (
            {"imageTags": ["test"], "image_uri": "test"},
            False,
        ),
        (
            {"image_uri": "test"},
            False,
        ),
    ],
)
def test_is_image_tagged_keep(image, result):
    assert (
        main.is_image_tagged_keep(
            image,
        )
    ) == result


@pytest.mark.parametrize(
    "image,images,result",
    [
        (
            {"image_uri": "test"},
            ["test"],
            True,
        ),
        (
            {"image_uri": "fail"},
            ["test"],
            False,
        ),
    ],
)
def test_is_image_referenced(image, images, result):
    assert (main.is_image_referenced(image, images)) == result


@pytest.mark.parametrize(
    "image,images,result",
    [
        (
            {
                "image_uri": "test",
                "imageTags": ["false"],
                "lastRecordedPullTime": UTC.localize(datetime.now() - timedelta(10)),
            },
            ["false"],
            True,
        ),
        (
            {
                "image_uri": "fail",
                "imageTags": ["keep"],
                "lastRecordedPullTime": UTC.localize(datetime.now() - timedelta(2)),
            },
            ["test"],
            False,
        ),
    ],
)
def test_is_image_deletable(image, images, result):
    assert (main.is_image_deletable(image, images)) == result
