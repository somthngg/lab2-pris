"""Пересчёт затрат, взвешенных оценок и экономии часов. python calculate.py."""
import json
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
BASE = Path(__file__).resolve().parent
D = lambda value: Decimal(str(value))

def fmt(value, digits=2):
    return f'{D(value).quantize(D(1).scaleb(-digits), rounding=ROUND_HALF_UP):,.{digits}f}'.replace(',', ' ').replace('.', ',')

def calculate(data):
    rate = D(data['it_monthly_reference_rub']) / data['it_month_hours']
    weekly = data['scenario_subjects'] * data['defenses_per_subject_week']
    annual = weekly * data['teaching_weeks_per_year']
    pilot = weekly * data['pilot_weeks']
    weights = [D(c['weight']) for c in data['criteria']]
    assert sum(weights) == 1
    variants = {}
    for key, item in data['variants'].items():
        hours = sum(item['hours'].values())
        direct = D(hours) * rate
        reserve = direct * D(data['reserve_rate'])
        support = D(item['annual_support_hours']) * rate
        delta = D(data['organisation_minutes_before']) - D(item['organisation_minutes_after'])
        variants[key] = dict(hours=hours, direct=direct, reserve=reserve, creation=direct+reserve,
            support_hours=item['annual_support_hours'], annual_cost=support,
            tco=direct+reserve+data['horizon_years']*support,
            annual_saved_hours=D(annual)*delta/60, pilot_saved_hours=D(pilot)*delta/60,
            score=sum(w*D(s) for w,s in zip(weights,data['scores'][key])), eligible=item['eligible'])
    sensitivity = []
    main = max(range(len(weights)),key=lambda i:weights[i])
    for delta in (D('-.05'),D('0'),D('.05')):
        changed = weights[main]+delta
        updated = [changed if i==main else w*(1-changed)/(1-weights[main]) for i,w in enumerate(weights)]
        assert abs(sum(updated)-1) < D('1e-20')
        scores = {k:sum(w*D(s) for w,s in zip(updated,data['scores'][k])) for k in variants}
        winner = max((k for k in variants if variants[k]['eligible']),key=lambda k:scores[k])
        sensitivity.append(dict(main_weight=changed, weights=updated, scores=scores, winner=winner))
    delta = D(data['organisation_minutes_before'])-D(data['variants']['C']['organisation_minutes_after'])
    scenarios = [dict(bookings=D(annual)*factor,saved_hours=D(annual)*factor*delta/60)
        for factor in (D('.5'),D('1'),D('1.5'))]
    return dict(it_hour_cost=rate, weekly_bookings=weekly, pilot_bookings=pilot, annual_bookings=annual,
        variants=variants, sensitivity=sensitivity, effect_scenarios=scenarios,
        roi=None, payback=None, financial_effect_note=data['financial_effect_note'])

def render(data, result):
    lines = ['# Расчёты концепции записи на защиту лабораторных','',
      'Часы, нагрузка и организационные минуты являются учебными оценками, а не результатами измерений. Смета отражает стоимость занятости ИТ-сотрудника. Дополнительных платежей за предоставленные вузом сервер и почту нет.','',
      '## Основание оценки труда ИТ-отдела','',
      'Условный месячный ориентир — 80 000 руб., расчётный месяц — 160 ч. В смете: 80 000 / 160 = 500 руб./ч.',
      f"Ориентир: [подборка вакансий Центра карьеры ИТМО]({data['cost_reference_url']}), содержащая предложение веб-разработчику от 80 тыс. руб./месяц. Это не зарплата конкретного сотрудника университета. Норма 160 ч и применение ориентира ко всем этапам — допущения. Полный фонд оплаты труда с начислениями не рассчитывается.",
      'Стоимость времени преподавателя и практиканта не задаётся. Экономия их времени в рубли не переводится.','',
      '## Затраты вариантов','', '| Показатель | A | B | C |','|---|---:|---:|---:|']
    for label,key in [('Работы, ч','hours'),('Работы, руб.','direct'),('Резерв, руб.','reserve'),('Запуск с резервом, руб.','creation'),('Поддержка, ч/год','support_hours'),('Поддержка, руб./год','annual_cost'),('TCO за 3 года, руб.','tco')]:
        lines.append('| '+label+' | '+' | '.join(fmt(result['variants'][k][key],0) for k in 'ABC')+' |')
    lines += ['', 'Запуск = часы работ × 500 × 1,10. Поддержка = часы поддержки × 500. TCO = запуск + 3 × поддержка.','',
      '## Состав трудоёмкости','']
    for key,item in data['variants'].items():
        lines += [f'### {key}. {item["name"]}','','| Работа | Часы |','|---|---:|']
        lines += [f'| {name} | {hours} |' for name,hours in item['hours'].items()]
        lines += ['',f"Поддержка: {item['annual_support_hours']} ч/год; до начала использования: {item['launch_weeks']} недель.",'']
    lines += ['Поддержка B оценена выше C из-за связи с обновлениями портала. Это плановая гипотеза, а не результат обследования конкретного кода.','',
      '## Взвешенные оценки','', '| Критерий | Вес | A, справочно | B | C |','|---|---:|---:|---:|---:|']
    for i,c in enumerate(data['criteria']):
        lines.append(f'| {c["id"]}. {c["name"]} | {fmt(c["weight"])} | '+' | '.join(str(data['scores'][k][i]) for k in 'ABC')+' |')
    lines += ['| Итог | 1,00 | '+' | '.join(fmt(result['variants'][k]['score']) for k in 'ABC')+' |','',
      'A исключён по обязательным требованиям; баллы B/C — экспертная оценка концепций, а не испытанных интерфейсов.','',
      '| Вес K1 | B | C | Лидер |','|---|---:|---:|---|']
    for row in result['sensitivity']:
        lines.append('| '+fmt(row['main_weight'])+' | '+fmt(row['scores']['B'],3)+' | '+fmt(row['scores']['C'],3)+' | '+row['winner']+' |')
    lines += ['', 'Остальные веса перенормированы пропорционально с сохранением суммы 1.','',
      '## Эффект в часах','',
      f"Пример: 3 предмета × 20 защит/неделю × 32 учебные недели = {result['annual_bookings']} защит в год. За четыре недели при той же нагрузке — {result['pilot_bookings']} защит. Это сценарий расчёта, а не квота системы.",
      'Пилот включает 1–3 предмета. Исходное организационное время — 1,5 минуты на запись; после внедрения B/C — 0,5 минуты. Это гипотезы для хронометража. Сами 10 минут защиты не включаются в экономию.','',
      '| Вариант | После, мин/запись | Экономия, ч/год | За 4 недели при 3 предметах, ч |','|---|---:|---:|---:|']
    for key,item in data['variants'].items():
        v=result['variants'][key]
        lines.append(f'| {key} | {fmt(item["organisation_minutes_after"],1)} | {fmt(v["annual_saved_hours"],1)} | {fmt(v["pilot_saved_hours"],1)} |')
    lines += ['', 'Для C: 1 920 × (1,5 − 0,5) / 60 = 32 ч/год; 240 × 1 / 60 = 4 ч за четыре недели.','',
      '| Защит в год | Экономия C, ч/год |','|---:|---:|']
    lines += [f'| {fmt(row["bookings"],0)} | {fmt(row["saved_hours"],0)} |' for row in result['effect_scenarios']]
    lines += ['', 'Денежный эффект не оценивается. ROI и срок окупаемости в принятой модели не определяются. Целесообразность обосновывается трудозатратами и улучшением организации приёма. Неизмеренный денежный эффект не подменяется нулём.','']
    return '\n'.join(lines)

if __name__ == '__main__':
    data=json.loads((BASE/'assumptions.json').read_text(encoding='utf-8'))
    result=calculate(data)
    (BASE/'results.md').write_text(render(data,result),encoding='utf-8')
    (BASE/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=float)+'\n',encoding='utf-8')
    print('Updated results.md and results.json')
