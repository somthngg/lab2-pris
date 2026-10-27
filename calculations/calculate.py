"""Пересчёт оценок и экономики: python calculate.py. Внешние пакеты не нужны."""
import json
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
BASE=Path(__file__).resolve().parent
def dec(x):return Decimal(str(x))
def fmt(x,n=2):
    if x is None:return 'не окупается'
    return f'{dec(x).quantize(Decimal(1).scaleb(-n),rounding=ROUND_HALF_UP):,.{n}f}'.replace(',',' ').replace('.',',')
def calculate(d):
    count=d['ordinary_months']*d['bookings_per_ordinary_month']+d['peak_months']*d['bookings_per_peak_month']
    weights=[dec(c['weight']) for c in d['criteria']]
    assert sum(weights)==1
    variants={}
    for key,v in d['variants'].items():
        hours=sum(v['hours'].values());direct=dec(hours)*d['project_hour_cost']
        reserve=direct*dec(d['reserve_rate']);creation=direct+reserve
        annual=sum(dec(c) for c in v['annual_costs'].values())
        saved=dec(count)*(dec(d['baseline_organisation_minutes'])-dec(v['residual_minutes']))/60
        effect=saved*d['teacher_hour_cost'];tco=creation+d['horizon_years']*annual;net=effect-annual
        score=sum(w*dec(s) for w,s in zip(weights,d['scores'][key]))
        variants[key]=dict(hours=hours,person_months=dec(hours)/d['hours_per_person_month'],direct=direct,
            reserve=reserve,creation=creation,annual=annual,tco=tco,saved_hours=saved,effect=effect,net=net,
            payback=creation/net if net>0 else None,roi=(d['horizon_years']*effect-tco)/tco*100,
            score=score,eligible=v['eligible'])
    sensitivity=[];main=max(range(len(weights)),key=lambda i:weights[i])
    for delta in [dec('-.05'),dec('0'),dec('.05')]:
        changed=weights[main]+delta
        w=[changed if j==main else old*(1-changed)/(1-weights[main]) for j,old in enumerate(weights)]
        assert abs(sum(w)-1)<dec('1e-20')
        scores={k:sum(x*dec(y) for x,y in zip(w,d['scores'][k])) for k in variants}
        winner=max((k for k in variants if variants[k]['eligible']),key=lambda k:scores[k])
        sensitivity.append(dict(main_weight=changed,weights=w,scores=scores,winner=winner))
    b=variants['B'];scenarios=[]
    for factor in [dec('.7'),dec('1'),dec('1.3')]:
        effect=b['effect']*factor;net=effect-b['annual']
        scenarios.append(dict(factor=factor,bookings=dec(count)*factor,effect=effect,net=net,
             roi=(d['horizon_years']*effect-b['tco'])/b['tco']*100,payback=b['creation']/net if net>0 else None))
    per_record=(dec(d['baseline_organisation_minutes'])-dec(d['variants']['B']['residual_minutes']))/60*d['teacher_hour_cost']
    threshold=(b['creation']/d['horizon_years']+b['annual'])/per_record if per_record>0 else None
    return dict(annual_bookings=count,variants=variants,sensitivity=sensitivity,scenarios=scenarios,breakeven_bookings=threshold)
def render(d,r):
    lines=['# Расчёты концепции ИС записи на консультации','',
      'Горизонт оценки - 3 года. Нагрузка является расчётным примером, а не ограничением числа пользователей или срока работы системы. Ставки труда и расходы размещения приняты для сметы.', '',
      '## Нагрузка и ставки','',
      f"Записи за год: {d['ordinary_months']} × {d['bookings_per_ordinary_month']} + {d['peak_months']} × {d['bookings_per_peak_month']} = {r['annual_bookings']}.",
      f"Организационное время преподавателя до изменений: {d['baseline_organisation_minutes']} мин на запись; стоимость часа: {d['teacher_hour_cost']} руб. Проектная работа: {d['project_hour_cost']} руб./ч.",
      'Время самой консультации (20 минут) не включается в экономию. Прямого уменьшения зарплатных выплат модель не предполагает.', '',
      '## Сводные результаты','', '| Показатель | A | B | C |','|---|---:|---:|---:|']
    rows=[('Трудоёмкость, ч','hours'),('Чел.-мес. при 160 ч','person_months'),('Работы, руб.','direct'),
      ('Резерв 10%, руб.','reserve'),('Первоначальные затраты, руб.','creation'),('Эксплуатация, руб./год','annual'),
      ('TCO за 3 года, руб.','tco'),('Высвобождение времени, ч/год','saved_hours'),
      ('Стоимость высвобождённого времени, руб./год','effect'),('Чистый условный эффект, руб./год','net'),
      ('Условный ROI за 3 года, %','roi'),('Условная окупаемость, лет','payback'),('Взвешенный балл','score')]
    for title,key in rows:lines.append('| '+title+' | '+' | '.join(fmt(r['variants'][v][key]) for v in 'ABC')+' |')
    lines+=['','Лицензионные платежи в вариантах равны нулю. Первоначальные затраты = часы × ставка × 1,10. TCO = первоначальные затраты + 3 × эксплуатация.',
       'E = число записей × сокращение организационного времени / 60 × стоимость часа. ROI = (3 × E - TCO) / TCO × 100%. Окупаемость = первоначальные затраты / (E - эксплуатация), если знаменатель положителен.',
       'Это оценка полезной трудовой мощности. При сохранении зарплат денежная окупаемость не подтверждается. A исключён из выбора по обязательным требованиям, его экономика приведена для сравнения.', '',
       '## Состав затрат','']
    for k,v in d['variants'].items():
        lines += [f'### {k}. {v["name"]}','','| Работа | Часы |','|---|---:|']
        lines += [f'| {name} | {h} |' for name,h in v['hours'].items()]
        lines += ['', '| Ежегодная статья | Руб./год |','|---|---:|']
        lines += [f'| {name} | {fmt(value)} |' for name,value in v['annual_costs'].items()];lines += ['']
    lines += ['## Оценки вариантов','','| Критерий | Вес | A, справочно | B | C |','|---|---:|---:|---:|---:|']
    for i,c in enumerate(d['criteria']):lines.append(f'| {c["id"]}. {c["name"]} | {fmt(c["weight"])} | '+' | '.join(str(d['scores'][v][i]) for v in 'ABC')+' |')
    lines += ['','## Устойчивость','','| Вес K1 | A, справочно | B | C | Лидер |','|---|---:|---:|---:|---|']
    for s in r['sensitivity']:lines.append('| '+fmt(s['main_weight'])+' | '+' | '.join(fmt(s['scores'][v],4) for v in 'ABC')+' | '+s['winner']+' |')
    lines += ['', 'Остальные веса перенормированы пропорционально: w′j = wj × (1 - w′1)/(1 - w1).', '',
      '## Чувствительность экономики B','','| Нагрузка | Записей/год | E, руб./год | Чистый эффект, руб./год | ROI, % | Окупаемость, лет |','|---|---:|---:|---:|---:|---:|']
    for s in r['scenarios']:lines.append('| '+fmt(s['factor']*100,0)+'% | '+fmt(s['bookings'],0)+' | '+fmt(s['effect'])+' | '+fmt(s['net'])+' | '+fmt(s['roi'])+' | '+fmt(s['payback'])+' |')
    threshold_text=(f"Порог трёхлетней условной окупаемости: {fmt(r['breakeven_bookings'])}, то есть не менее {r['breakeven_bookings'].to_integral_value(rounding=ROUND_CEILING)} записей в год при неизменных расходах и экономии времени."
                    if r['breakeven_bookings'] is not None else 'При отсутствии положительной экономии времени порог окупаемости по этой модели не достигается.')
    lines += ['',threshold_text,
      'Расходы оставлены постоянными в пределах одного стенда и расчётной нагрузки. Расширение инфраструктуры оценивается отдельно.', '',
      '## Условный накопленный результат B','','| Момент | Расходы, руб. | Стоимость времени, руб. | Накопленный результат, руб. |','|---|---:|---:|---:|',
      f"| Запуск | {fmt(r['variants']['B']['creation'])} | 0,00 | {fmt(-r['variants']['B']['creation'])} |"]
    for year in range(1,4):
        b=r['variants']['B'];lines.append(f'| Год {year} | {fmt(b["annual"])} | {fmt(b["effect"])} | {fmt(-b["creation"]+year*b["net"])} |')
    return '\n'.join(lines)+'\n'
if __name__=='__main__':
    data=json.loads((BASE/'assumptions.json').read_text(encoding='utf-8'));result=calculate(data)
    (BASE/'results.md').write_text(render(data,result),encoding='utf-8')
    (BASE/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=float)+'\n',encoding='utf-8')
    print('Saved results.md and results.json')
