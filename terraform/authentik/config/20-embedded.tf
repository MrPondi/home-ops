resource "authentik_outpost" "embedded" {
  name = "authentik Embedded Outpost"

  protocol_providers = [
    authentik_provider_proxy.bazarr.id
  ]
}
