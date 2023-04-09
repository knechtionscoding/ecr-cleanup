# ecr-cleanup

Deploys a job that cleans up an ECR repo based on the following rules.
1. Is a container currently referenced in the same K8s cluster that this job is running in
2. Has the container been pulled in the last 7 days
3. Has the container been tagged with the word `keep`
4. Is the container the only tag in the ECR repository

![Version: 0.3.0](https://img.shields.io/badge/Version-0.3.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.3.0](https://img.shields.io/badge/AppVersion-0.3.0-informational?style=flat-square)

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| awsRegistryId | string | `""` | ECR Registry ID to override picking the default |
| command | list | `["/code/main.py"]` | Command being run by the cronjob |
| dryRun | bool | `false` | Should the tool run in dryrun |
| extraEnvs | object | `{}` |  |
| fullnameOverride | string | `""` | Override fullname |
| image.pullPolicy | string | `"IfNotPresent"` | Pull Policy for images in cronjob |
| image.registry | string | `"ghcr.io"` | Image Registry |
| image.repository | string | `"knechtionscoding/ecr-cleanup"` | Image Repository |
| image.tag | string | `""` | Overrides the image tag whose default is the chart appVersion. |
| imagePullSecrets | list | `[]` | List of imagePullSecrets to use when getting images |
| logLevel | string | `"INFO"` | Configure Log level of application |
| nameOverride | string | `""` | Overriding the Name |
| podAnnotations | object | `{}` | Annotations to add to the pod |
| podSecurityContext | object | `{}` | Security Context for Pod |
| resources | object | `{}` | Resources for container in cronjob |
| schedule | string | `"* 0 * * * "` |  |
| securityContext | object | `{}` | Security Context for container in cronjob |
| serviceAccount.annotations | object | `{}` | Annotations to add to the service account |
| serviceAccount.create | bool | `true` | Specifies whether a service account should be created |
| serviceAccount.name | string | `""` | The name of the service account to use. If not set and create is true, a name is generated using the fullname template |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.11.0](https://github.com/norwoodj/helm-docs/releases/v1.11.0)