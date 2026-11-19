# Platform MVP: Architecture & Tech Stack Choices

> **Instructions:** Mark your choices by putting an `x` inside the bracket (e.g. `[x]`).

---

### 1. Platform Control Plane & UI (The Engine)
- [x] **TypeScript (Node.js / Express or Next.js)** — Lightweight, transparent, easy UI/API unification, mirrors Backstage
- [ ] **Python (FastAPI)** — Simple scripting, clean REST API, native `boto3` support
- [ ] **Go (Golang)** — Fast, single binary, standard cloud-native systems language
- [ ] **Spotify Backstage** — CNCF standard portal framework, enterprise/heavyweight

---

### 2. Golden Path Template Configuration (The Blueprint)
- [x] **YAML (`template.yaml`)** — Universal platform engineering standard (Backstage, K8s, CI/CD)
- [ ] **JSON** — Machine-readable format, strict, lacks comments
- [ ] **CUE / Pkl** — Type-safe configuration and validation language

---

### 3. Infrastructure Provisioning (S3 Golden Path)
- [x] **Terraform / OpenTofu (HCL)** — Declarative, state-managed, industry-standard IaC
- [ ] **Direct AWS SDK** — Imperative API calls, zero CLI tools to install, manual state handling
- [ ] **AWS CDK / Pulumi** — Code-based IaC (TypeScript or Python)
- [ ] **Crossplane** — Kubernetes-native control plane

---

### 4. Pipeline Execution Glue (GitHub ➔ Platform ➔ S3)
- [x] **Local Process Runner (Shell / Node / Python worker)** — Step-by-step visibility into clone ➔ terraform ➔ s3 upload locally
- [ ] **GitHub Actions** — Cloud runner triggered via repository dispatch / webhooks

---

### 5. Target S3 Environment
- [x] **LocalStack** — Free local S3 emulator, no AWS credentials or billing risk
- [ ] **Live AWS Account** — Deploys to a real public AWS S3 bucket endpoint
