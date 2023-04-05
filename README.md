# ECR-Image-Cleanup

This cleans up an ECR repo based on the following rules.

1. Is a container currently referenced in the same K8s cluster that this job is running in
2. Has the container been pulled in the last 7 days
3. Has the container been tagged with the word `keep`
4. Is the container the only tag in the ECR repository

## Deployment

### Helm

```bash
helm repo add knechtionscoding https://knechtionscoding.github.io/ecr-cleanup/ && helm repo update
helm install ecr-cleanup knechtionscoding/ecr-cleanup --set awsRegistryId=<accountId>
```

## Development

### Pre-Requisites

- `pre-commit`
- `poetry`

### Running

- `make run`

#### GovCloud

**NOTE: In GovCloud you have to manually get the ecr registry id and set it: `AWS_REGISTRY_ID` this is the numbers prior to the .ecr in an image, eg: in `000000000000.dkr.ecr-fips.us-gov-west-1.amazonaws.com/<image>:<tag>` it would be: `000000000000`**

- `AWS_REGISTRY_ID=thing make run`

#### Dry Run

- `make dry-run`

## Example Images Dict

```python
{
    'registryId': 'string',
    'repositoryName': 'string',
    'imageDigest': 'string',
    'imageTags': [
        'string',
    ],
    'imageSizeInBytes': 123,
    'imagePushedAt': datetime(2015, 1, 1),
    'imageScanStatus': {
        'status': 'IN_PROGRESS'|'COMPLETE'|'FAILED'|'UNSUPPORTED_IMAGE'|'ACTIVE'|'PENDING'|'SCAN_ELIGIBILITY_EXPIRED'|'FINDINGS_UNAVAILABLE',
        'description': 'string'
    },
    'imageScanFindingsSummary': {
        'imageScanCompletedAt': datetime(2015, 1, 1),
        'vulnerabilitySourceUpdatedAt': datetime(2015, 1, 1),
        'findingSeverityCounts': {
            'string': 123
        }
    },
    'imageManifestMediaType': 'string',
    'artifactMediaType': 'string',
    'lastRecordedPullTime': datetime(2015, 1, 1)
}
```

## Example Run

```txt
Getting Daemonsets from the K8s API
INFO:ecr-image-cleanup:Getting Daemonsets from the K8s API
Getting Deployments from the K8s API
INFO:ecr-image-cleanup:Getting Deployments from the K8s API
Getting Statefulset from the K8s API
INFO:ecr-image-cleanup:Getting Statefulset from the K8s API
Getting Cronjobs from the K8s API
INFO:ecr-image-cleanup:Getting Cronjobs from the K8s API
Getting Jobs from the K8s API
INFO:ecr-image-cleanup:Getting Jobs from the K8s API
Getting Pods from the K8s API
INFO:ecr-image-cleanup:Getting Pods from the K8s API
000000000000.dkr.ecr-fips.us-gov-west-1.amazonaws.com/test/test-image:not-latest was found in k8s workload
INFO:ecr-image-cleanup:000000000000.dkr.ecr-fips.us-gov-west-1.amazonaws.com/test/test-image:not-latest was found in k8s workload
000000000000.dkr.ecr-fips.us-gov-west-1.amazonaws.com/test/test-image:latest was not found in k8s workload
INFO:ecr-image-cleanup:000000000000.dkr.ecr-fips.us-gov-west-1.amazonaws.com/test/test-image:latest was not found in k8s workload
000000000000.dkr.ecr-fips.us-gov-west-1.amazonaws.com/test/test-image:latest was not tagged keep
INFO:ecr-image-cleanup:000000000000.dkr.ecr-fips.us-gov-west-1.amazonaws.com/test/test-image:latest was not tagged keep
...
Deleting 000000000000.dkr.ecr-fips.us-gov-west-1.amazonaws.com/test/test-image:latest
INFO:ecr-image-cleanup:Deleting 000000000000.dkr.ecr-fips.us-gov-west-1.amazonaws.com/test/test-image:latest
...
```
