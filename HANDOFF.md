# هنداف (Handoff) — Smart Grid Trading Bot

## خلاصه پروژه
بات گرید هوشمند مبتنی بر ATR برای متاتریدر ۵ (Python / `MetaTrader5`).
گرید چندسطحی پاندینگ (Buy/Sell Stop) دورِ قیمت انکر کاشته میشود؛ با پر شدن پلهها، عمق گرید بهصورت مرحلهای تا `grid_count` رشد میکند و یک «سبد» سود از کل پوزیشنهای همجهت بهصورت تیپی مشترک هدفگذاری میشود. اکسپوژر خالص تعیینکننده جهت تارگت است.

## وضعیت فعلی (قابل آزمایش — ۷۱ تست پاس)
اجرا: `python -m pytest tests/ -q` → `71 passed`.

### تازهترین کار (TP محوری — هرگز پشت ورود)
Objective: «از همان شروع، تیپی روی همه پلهها؛ تیپی هرگز پشت پوزیشن؛ اصلاح اسلیپیج در حین کار».

- `mt5_client/order_service.py` — `send_pending_order_with_retry` پارامترهای `sl/tp` گرفت و به ریکوئست پندر پاس میدهد.
- `strategy/grid_builder.py` — `build_orders` و `build_orders_for_depth` کلید `tp` ساختند (پارامتر `grid_step`): خرید `price+step`، فروش `price−step`.
- `strategy/cycle_manager.py::_place_grid_depths` — تیپی را از روی `sc.effective_grid_step` (فالبک `tick_size`) میسازد، پاس میدهد و لاگ میکند (هم در مسیر واقعی و هم dry-run).
- `strategy/cycle_manager.py::_set_basket_targets` — **هسته رفع**:
  - پوزیشن همجهت خرید: `tp = max(target, entry + step)`
  - پوزیشن همجهت فروش: `tp = min(target, entry − step)`
  - سمت هج (SL): خرید `min(target, entry − step)`، فروش `max(target, entry + step)` — SL هم پشت ورود نمینشیند.
  - با این قاعده، پوزیشنی که ورودش فراتر از تیپی پویاست، تیپی محلی `entry±1step` میگیرد؛ بقیه تیپی مشترک سبد.
- `._keep_target_on_grid` — حفظ شد (کلَمپ تارگت به آخرین سطح کاشتهشده). با قاعده بالا دیگر موجب «تیپی پشت پوزیشن» نمیشود.
- تصمیم کاربر: **کاشت اولیه `base+1` حفظ شد** (یک سطح بعد از برخورد تارگت).

### کارهای از-پیش-موجود (WIP که در همین کامییتها هست)
- `main.py` — رفع کرش خاموشی: `get_all_cycle_records` → `get_all_cycles`.
- `mt5_client/position_service.py` — بستن پوزیشن با چند حالت filling (IOC/FOK/RETURN).
- `strategy/target_calculator.py` — `contract_size` به همه توابع منتقل شد (فالبک دیگر ۱۰۰ هاردکد نیست).
- `strategy/grid_builder.py` — `calculate_initial_depths` (کاشت `base+1`، سقف `max_grid_count`) و `estimate_needed_depths` (رشد مرحلهای سمت غالب).
- `utils/logger.py` — متد `Logger.text()` برای فایل `grid_decisions.txt`.

## معماری کلیدی
- `strategy/grid_builder.py` — ساخت قیمت گرید، محاسبه عمق لازم (`_solve_needed_depth`)، ساخت سفارشها.
- `strategy/cycle_manager.py` — ماشین وضعیت هر سمبل (STATE: preparing → placing_grid → grid_active → positions_active → target_active → locked_exposure → closing → resetting)؛ مدیریت تارگت/اجرای گرید.
- `strategy/target_calculator.py` — محاسبه تیپی سبد با براکتگیری + بایسکت روی `order_calc_profit`.
- `strategy/basket_manager.py` — تشخیص قفل اکسپوژر (`is_locked_exposure`)، انتخاب پوزیشن تریگر.
- `strategy/atr.py` — محاسبه ATR و فیلتر ورود.
- `mt5_client/*` — connection, market_data, order_service, position_service, account_service, history_service.
- `services/persistence.py` — ذخیره سیکلها (`get_all_cycles`).
- `config/*` — مدلها، لودر، setup تعاملی. `models/*` — context/order/enums.

## اجرا و تنظیم
- `config.yaml`: سمبلها با `grid_count`, `lot_size`, `target_profit`, `magic_number`, `commission_per_position`, `atr_*`.
- `data/user_defaults.yaml` از git حذف شده (در `.gitignore`). لاگها در `logs/`.
- حالت تست: `dry_run: true` در `config.yaml` یا اجرای مربوطه؛ سفارشها فقط لاگ میشوند.
- حساب **Hedging** لازم است.

## نکات اجرایی (از اجرای واقعی ۲۰۲۶-۰۸-۰۵ روی NAS100)
- بروکر ممکن است گام گرید را به `trade_stops_level * tick` بالاتر از مقدار ATR قفل کند.
- هشدار: عدم تطابق خطوط لاگ `ticket=... price=...` با کد فعلی نشان میدهد نمونه در حال اجرا از نسخه قدیمیتر بود؛ قبل از اعتماد به لاگ، نسخه را هماهنگ کنید.

## ادامه کار (پیشنهاد)
- تست زنده با `--dry-run` / `dry_run: true` برای دیدن تیپیهای اولیه و رفتار بازنویسی.
- بررسی رفتار وقتی `target` اولینبار قبل از کاملشدن رشد گرید محاسبه میشود (ترتیب `_try_set_basket_target` و `_grow_grid_depth_if_needed`).
- invalid-TP rejection توسط بروکر وقتی ورود با اسلیپیج خیلی دور است (گارد با `min_stop_distance`).
- شخصیسازی `grid_decisions.txt` و لاگ تیپیهای مؤثر هر پوزیشن.

## Git
- ریموت: `origin → https://github.com/majidpaksima/SmartGrid.git`
- شاخه: `main`
- `.gitignore` شامل `logs/`, `data/user_defaults.yaml`, `data/bot.db`, `*.env`.