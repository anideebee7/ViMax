# Deploy ViMax to Amazon EKS

Deploy **ViMax API** and **Frontend** to EKS: build prod images, push to ECR, apply Kubernetes manifests.

## Prerequisites

- EKS cluster (1.27+), `kubectl` configured
- [AWS Load Balancer Controller](https://docs.aws.amazon.com/eks/latest/userguide/aws-load-balancer-controller.html) installed
- ECR repos: `vimax-api`, `vimax-frontend`

## 1. Create ECR repositories

```bash
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=us-east-1
aws ecr create-repository --repository-name vimax-api      --region $AWS_REGION
aws ecr create-repository --repository-name vimax-frontend --region $AWS_REGION
```

## 2. Build and push images

### API

```bash
docker build -t $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/vimax-api:latest .
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com
docker push $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/vimax-api:latest
```

### Frontend (production)

Set the API URL the browser will use (e.g. `https://api.vimax.example.com`):

```bash
docker build -f frontend/Dockerfile.prod \
  --build-arg VITE_API_URL=https://api.vimax.example.com \
  -t $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/vimax-frontend:latest \
  ./frontend
docker push $AWS_ACCOUNT.dkr.ecr.$AWS_REGION.amazonaws.com/vimax-frontend:latest
```

## 3. Namespace and ConfigMap

```bash
kubectl apply -f deploy/eks/namespace.yaml
kubectl apply -f deploy/eks/configmap.yaml
```

## 4. Secret from .env

```bash
kubectl create secret generic vimax-api-secret --namespace=vimax --from-env-file=.env
```

Or from literals (see `.env.example` for keys): `XAI_API_KEY`, `GEMINI_API_KEY`, `PIAPI_API_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `ELEVENLABS_API_KEY`, etc.

## 5. Set image and apply

Replace `000000000000.dkr.ecr.us-east-1.amazonaws.com` in `api-deployment.yaml` and `frontend-deployment.yaml` with your ECR URL, then:

```bash
kubectl apply -f deploy/eks/api-deployment.yaml
kubectl apply -f deploy/eks/api-service.yaml
kubectl apply -f deploy/eks/frontend-deployment.yaml
kubectl apply -f deploy/eks/frontend-service.yaml
```

## 6. Ingress and DNS

Edit `ingress.yaml`: set `host` to your domain (`vimax.example.com`, `api.vimax.example.com`). For HTTPS, set `alb.ingress.kubernetes.io/certificate-arn` and `alb.ingress.kubernetes.io/ssl-redirect: "443"`.

```bash
kubectl apply -f deploy/eks/ingress.yaml
kubectl get ingress -n vimax
```

Point DNS (CNAME) for `vimax.example.com` and `api.vimax.example.com` to the ALB hostname.

## 7. ECR access

Use IRSA for the `vimax` service account, or create `imagePullSecrets` and add `imagePullSecrets: - name: ecr-registry` to the Deployments.

## Files

| File | Purpose |
|------|---------|
| `namespace.yaml` | `vimax` namespace |
| `configmap.yaml` | Non-sensitive API env |
| `secret.yaml` | Notes to create `vimax-api-secret` from `.env` |
| `api-deployment.yaml` | API Deployment |
| `api-service.yaml` | API Service |
| `frontend-deployment.yaml` | Frontend Deployment (prod image) |
| `frontend-service.yaml` | Frontend Service |
| `ingress.yaml` | ALB Ingress |

## Production frontend build

The frontend is built with `frontend/Dockerfile.prod`: multi-stage Node build + nginx. `VITE_API_URL` must be set at **build** time to the public API URL (e.g. `https://api.vimax.example.com`).
