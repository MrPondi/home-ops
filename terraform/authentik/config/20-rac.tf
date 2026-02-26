resource "authentik_outpost" "rac" {
  name = "RAC Outpost"
  protocol_providers = [authentik_provider_rac.pelican-wings.id]
  service_connection = data.authentik_service_connection_kubernetes.local.id
  type = "rac"
  config = jsonencode({
    "log_level": "info",
    "refresh_interval": "minutes=5",
    "authentik_host": "https://auth.pondi.dev/",
    "authentik_host_browser": "",
    "object_naming_template": "ak-outpost-%(name)s",
    "kubernetes_replicas": 1,
    "kubernetes_namespace": "security",
    "authentik_host_insecure": false,
    "kubernetes_json_patches": null,
    "kubernetes_service_type": "ClusterIP",
    "kubernetes_disabled_components": ["ingress"],
    "kubernetes_httproute_annotations": {},
    "kubernetes_httproute_parent_refs": [{
      "name": "envoy-internal",
      "namespace": "network"
    }],
  })
}