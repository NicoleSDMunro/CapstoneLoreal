# Smart Launch — Supply Chain Dashboard
**L'Oréal Brasil · Smart Launch & Responsiveness to Growth**

Dashboard interativo de análise de forecast e supply chain com visão por revisão (rolling forecast) e acurácia vintage.

---

## Instalação

```bash
# 1. Clone o repositório
git clone https://github.com/SEU_USUARIO/smart-launch.git
cd smart-launch

# 2. Instale as dependências
npm install

# 3. Rode localmente
npm run dev
```

Acesse em `http://localhost:5173`

---

## Build para produção

```bash
npm run build
```

Os arquivos ficam em `/dist` — prontos para hospedar no GitHub Pages ou Vercel.

---

## Deploy no Vercel (recomendado)

1. Suba o projeto para um repositório GitHub
2. Acesse [vercel.com](https://vercel.com) e clique em **Import Project**
3. Conecte o repositório
4. Clique em **Deploy** — pronto

---

## Deploy no GitHub Pages

```bash
# Instale o pacote gh-pages
npm install --save-dev gh-pages

# Adicione ao package.json:
# "homepage": "https://SEU_USUARIO.github.io/smart-launch",
# "predeploy": "npm run build",
# "deploy": "gh-pages -d dist"

npm run deploy
```

---

## Estrutura do projeto

```
smart-launch/
├── index.html
├── package.json
├── vite.config.js
└── src/
    ├── main.jsx
    ├── App.jsx          ← componente principal
    └── data/
        ├── produtos.js  ← configurações e metadados dos produtos
        └── series.js    ← matrizes de forecast (PV, Produção, Estoque)
```

---

## Como adicionar mais produtos

Em `src/data/produtos.js`, adicione o produto em `PI`:
```js
F: { o: "Interno", c: 26, l: 24, d: "Queda" },
```

Em `src/data/series.js`, adicione a matriz de dados:
```js
const DF = { pv: [[...], ...], prod: [[...], ...], est: [[...], ...] }
```

E exporte no `DMAP`:
```js
export const DMAP = { A: DA, B: DB, C: DC, D: DD, E: DE, F: DF }
```

Por fim, adicione `"F"` ao array `PRODS` em `produtos.js`.

---

## Tecnologias

- [React 18](https://react.dev)
- [Recharts](https://recharts.org)
- [Vite](https://vitejs.dev)
