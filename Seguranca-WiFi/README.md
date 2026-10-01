# Auditoria de segurança da sua rede Wi‑Fi

Ferramenta **defensiva** para testar a segurança da **sua própria** rede. Faz um
inventário dos dispositivos conectados, verifica a criptografia/senha do Wi‑Fi e,
opcionalmente, procura portas abertas nos seus equipamentos. Não quebra senhas,
não captura tráfego de terceiros e não ataca nenhum alvo.

> ⚠️ **Uso legal:** rode somente na rede que você controla e com autorização de
> quem responde por ela. Testar rede alheia sem permissão por escrito é crime
> (Lei 12.737/2012 e Lei 14.155/2021).

## Como rodar (Windows)

1. Abra o **PowerShell como Administrador** (menu Iniciar → digite *PowerShell* →
   botão direito → **Executar como administrador**).
2. Libere a execução só para esta sessão:
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   ```
3. Vá até a pasta e execute:
   ```powershell
   cd caminho\para\security-tools
   .\Auditar-WiFi.ps1
   ```
   Para incluir o scan de portas:
   ```powershell
   .\Auditar-WiFi.ps1 -ScanPortas
   ```

Ao final, um relatório `.txt` é salvo na sua Área de Trabalho.

## O que é verificado

| # | Área | O que faz |
|---|------|-----------|
| 1 | **Dispositivos** | Descobre IP, MAC e nome dos aparelhos na rede, para você achar intrusos |
| 2 | **Criptografia/senha** | Checa WPA2/WPA3, comprimento e trivialidade da senha dos perfis salvos |
| 3 | **Portas** | (`-ScanPortas`) Procura portas de risco abertas nos seus equipamentos |

No fim ainda imprime um **checklist de hardening do roteador** (senha padrão, WPS,
firmware, admin remoto, UPnP, rede de visitantes).

## Próximos passos sugeridos
- Compare a lista de dispositivos com os clientes DHCP no painel do roteador.
- Desligue WPS e administração remota.
- Use senha de Wi‑Fi longa (15+ caracteres) em WPA2/WPA3.
