# Kubernetes Deployment

This directory contains Kubernetes manifests for deploying the Monitoring Dashboard.

## 📁 Files

- `namespace.yaml` - Dedicated namespace for the application
- `configmap.yaml` - Non-sensitive configuration
- `secret.yaml` - Sensitive credentials (SECRET_KEY, ENCRYPTION_KEY)
- `persistentvolumeclaim.yaml` - Storage for SQLite database
- `deployment.yaml` - Application deployment with health checks
- `service.yaml` - ClusterIP service
- `ingress.yaml` - Optional ingress for external access
- `kustomization.yaml` - Kustomize configuration

## 🐳 Container Image Setup

Before deploying, you need to make the container image available to your Kubernetes cluster.

### Option 1: Local Development (Minikube/Kind)

```bash
# Build the image
docker build -t monitoring-dashboard:latest .

# Load into Minikube
minikube image load monitoring-dashboard:latest

# OR load into Kind
kind load docker-image monitoring-dashboard:latest --name <cluster-name>

# Verify image is available
minikube image ls | grep monitoring-dashboard
# OR for Kind: docker exec -it <kind-node> crictl images | grep monitoring-dashboard
```

### Option 2: Docker Hub

```bash
# Build and tag
docker build -t monitoring-dashboard:latest .
docker tag monitoring-dashboard:latest username/monitoring-dashboard:latest

# Login and push
docker login
docker push username/monitoring-dashboard:latest

# Update deployment.yaml:
# image: docker.io/username/monitoring-dashboard:latest
```

### Option 3: GitHub Container Registry (GHCR)

```bash
# Build and tag
docker build -t monitoring-dashboard:latest .
docker tag monitoring-dashboard:latest ghcr.io/username/monitoring-dashboard:latest

# Login and push
echo $GITHUB_TOKEN | docker login ghcr.io -u username --password-stdin
docker push ghcr.io/username/monitoring-dashboard:latest

# Update deployment.yaml:
# image: ghcr.io/username/monitoring-dashboard:latest

# If private, create imagePullSecret:
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=username \
  --docker-password=$GITHUB_TOKEN \
  -n monitoring-dashboard

# Add to deployment.yaml under spec.template.spec:
# imagePullSecrets:
# - name: ghcr-secret
```

### Option 4: Private Registry

```bash
# Build and tag
docker build -t monitoring-dashboard:latest .
docker tag monitoring-dashboard:latest registry.example.com/monitoring-dashboard:latest

# Login and push
docker login registry.example.com
docker push registry.example.com/monitoring-dashboard:latest

# Create pull secret
kubectl create secret docker-registry registry-secret \
  --docker-server=registry.example.com \
  --docker-username=user \
  --docker-password=pass \
  -n monitoring-dashboard

# Update deployment.yaml:
# image: registry.example.com/monitoring-dashboard:latest
# imagePullSecrets:
# - name: registry-secret
```

---

## 🚀 Quick Deploy

### Method 1: Using kubectl

```bash
# 1. Generate secrets
export SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
export ENCRYPTION_KEY=$(cd .. && python3 generate_key.py)

# 2. Update secret.yaml with generated values
sed -i "s/REPLACE_WITH_YOUR_SECRET_KEY/$SECRET_KEY/g" secret.yaml
sed -i "s/REPLACE_WITH_YOUR_ENCRYPTION_KEY/$ENCRYPTION_KEY/g" secret.yaml

# 3. Apply all manifests
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml
kubectl apply -f persistentvolumeclaim.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml  # Optional

# 4. Verify deployment
kubectl get all -n monitoring-dashboard
kubectl logs -f deployment/monitoring-dashboard -n monitoring-dashboard
```

### Method 2: Using Kustomize

```bash
# 1. Update secret.yaml with your values first
# 2. Deploy with kustomize
kubectl apply -k .

# 3. Check status
kubectl get all -n monitoring-dashboard
```

### Method 3: Using kubectl with single command

```bash
kubectl apply -f . -n monitoring-dashboard
```

## 🔧 Configuration

### Before Deployment

1. **Update secret.yaml:**
   ```bash
   # Generate keys
   python3 -c 'import secrets; print(secrets.token_hex(32))'
   python3 generate_key.py
   
   # Edit secret.yaml and replace placeholders
   ```

2. **Configure ingress.yaml** (if using):
   - Update `host` with your domain
   - Configure TLS if needed
   - Adjust annotations for your ingress controller

3. **Adjust resources** in `deployment.yaml`:
   - Memory limits based on your needs
   - CPU limits based on your cluster

4. **Storage class** in `persistentvolumeclaim.yaml`:
   - Uncomment and set `storageClassName` if needed

## 📊 Monitoring

### Check Pod Status
```bash
kubectl get pods -n monitoring-dashboard
kubectl describe pod <pod-name> -n monitoring-dashboard
```

### View Logs
```bash
kubectl logs -f deployment/monitoring-dashboard -n monitoring-dashboard
```

### Health Check
```bash
kubectl port-forward svc/monitoring-dashboard 8000:80 -n monitoring-dashboard
curl http://localhost:8000/healthcheck
```

## 🔄 Updates

### Update Image
```bash
# Using kubectl
kubectl set image deployment/monitoring-dashboard \
  monitoring-dashboard=monitoring-dashboard:v1.0.1 \
  -n monitoring-dashboard

# Using kustomize
kustomize edit set image monitoring-dashboard=monitoring-dashboard:v1.0.1
kubectl apply -k .
```

### Rolling Restart
```bash
kubectl rollout restart deployment/monitoring-dashboard -n monitoring-dashboard
kubectl rollout status deployment/monitoring-dashboard -n monitoring-dashboard
```

## 🗑️ Cleanup

```bash
# Delete all resources
kubectl delete -f . -n monitoring-dashboard

# Or delete namespace (removes everything)
kubectl delete namespace monitoring-dashboard
```

## 🔒 Security Notes

1. **Never commit secret.yaml with real credentials**
   - Use sealed-secrets, external-secrets, or vault
   - Or create secrets imperatively

2. **Use RBAC** - Limit access to the namespace

3. **Network Policies** - Consider adding network policies to restrict traffic

4. **Image Security** - Scan images for vulnerabilities before deployment

## 🔄 CI/CD - Automated Image Publishing

### GitHub Actions Example

Create `.github/workflows/docker-publish.yml`:

```yaml
name: Build and Push Docker Image

on:
  push:
    branches: [ main, develop ]
    tags: [ 'v*' ]
  pull_request:
    branches: [ main ]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: ${{ github.event_name != 'pull_request' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

---

## 📝 Production Considerations

- [ ] Use external database (PostgreSQL) instead of SQLite
- [ ] Implement proper secret management (Vault, Sealed Secrets)
- [ ] Add HorizontalPodAutoscaler for scaling
- [ ] Configure resource requests/limits based on actual usage
- [ ] Set up monitoring (Prometheus/Grafana)
- [ ] Configure backups for PVC
- [ ] Add network policies
- [ ] **Use specific image tags instead of `:latest`**
- [ ] Configure pod disruption budgets
- [ ] Add pod anti-affinity for high availability
- [ ] **Set imagePullPolicy to `Always` for production**
- [ ] **Use private registry with imagePullSecrets**
