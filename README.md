 ## Config file format  'config.yaml'
```yaml
global_host: "<Global host for all routes eg: https://example.com>"
ip_header: X-Forwarded-For # header to look IPs for throtling
throttle_key_header: X-User-ID # Additional throttling key header
retry_config: # Retry if backend server result in 500 error
  max_retries: 3
  retry_delay: 2  # in seconds
global_throttle:
  max_connections: 200
  requests_per_minute: 100
  requests_per_hour: 2000
ip_whitelist: # Throttle exception IPs
  - 192.168.1.100
  - 10.0.0.1
allowed_urls:
  - source: /a
    host: https://example2.com  # Host override
    destination: /a/b
    methods:
      - GET
      - POST
    throttle:
      max_connections: 1
      requests_per_minute: 2
  - source: /b
    destination: /c
    methods:
      - GET
```
