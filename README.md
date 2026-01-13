# OEE Shopfloor Mnemo (Streamlit)

Демо-проект мнемосхемы цеха для 3 станков (ЧПУ) с индикацией состояния:
- 🟢 RUN (работает)
- ⚪ IDLE (не в работе)
- 🔴 DOWN (ремонт/ТО)

## Запуск
```bash
последовательность команд для Windows PowerShell 
cd path\to\oee-shopfloor-mnemo

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
streamlit run app.py

Windows PowerShell: .\.venv\Scripts\Activate.ps1

Windows CMD: .\.venv\Scripts\activate.bat

macOS/Linux: source .venv/bin/activate
