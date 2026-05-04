{{/*
Expand chart name.
*/}}
{{- define "wingman.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Full image reference: registry/repository:tag
If registry is empty, returns repository:tag
*/}}
{{- define "wingman.image" -}}
{{- $reg := .reg -}}
{{- $repo := .repo -}}
{{- $tag := .tag | default "latest" -}}
{{- if $reg -}}
  {{- printf "%s/%s:%s" $reg $repo $tag -}}
{{- else -}}
  {{- printf "%s:%s" $repo $tag -}}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "wingman.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: wingman
{{- end }}

{{/*
Selector labels for a component
*/}}
{{- define "wingman.selectorLabels" -}}
app.kubernetes.io/name: wingman
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: {{ . }}
{{- end }}

{{/*
Namespace — use override if set, else release namespace
*/}}
{{- define "wingman.namespace" -}}
{{- .Values.namespace | default .Release.Namespace }}
{{- end }}

{{/*
ServiceAccount name
*/}}
{{- define "wingman.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
  {{- .Values.serviceAccount.name | default "wingman" }}
{{- else }}
  {{- .Values.serviceAccount.name | default "default" }}
{{- end }}
{{- end }}

{{/*
OAuth redirect URI — use explicit value or derive from route.host
*/}}
{{- define "wingman.oauthRedirectUri" -}}
{{- if .Values.auth.oauthRedirectUri -}}
  {{- .Values.auth.oauthRedirectUri -}}
{{- else if .Values.openshiftRoute.enabled -}}
  {{- printf "https://%s/login" .Values.route.host -}}
{{- else if .Values.ingress.enabled -}}
  {{- printf "http://%s/login" .Values.ingress.host -}}
{{- else -}}
  {{- "" -}}
{{- end }}
{{- end }}

{{/*
True if a CA bundle is configured
*/}}
{{- define "wingman.hasCA" -}}
{{- if .Values.tls.caBundle -}}true{{- end }}
{{- end }}
