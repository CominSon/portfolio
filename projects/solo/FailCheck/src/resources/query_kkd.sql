/*
 Запрос на список по отчетам и информации по рассылкам
 */
select owner_surname,
       table_name,
       dash_name,
       mail_to,
       mail_copy,
       date_update,
       user_login from s_grnplm_ld_blago_ubhq_in.kkd_addressbook
;

/*
 Запрос на общую статистику по проверкам (по объекту)
 */

with backup as (
	select objects_name, max(date_start) as date_start
		from logs_backup_all_schedule
		where scripts = 'KKD'
		group by objects_name
)
, table_group as (
		select table_name, max(date_check) as date_start
				from s_grnplm_ld_blago_ubhq_in.kkd_logs_deviations
				group by table_name
)
, fight_table as (
	select kkd1.*
		from s_grnplm_ld_blago_ubhq_in.kkd_logs_deviations kkd1
		join table_group kkd2
			on kkd1.table_name = kkd2.table_name
			and kkd1.date_check =kkd2.date_start

)


select
	table_name,
	name_check,
	count(1) as all_checks,
	count(case when check_result in ('Отклонение', 'Есть изменение') then 1 end) as count_change_result,
	concat(round(100.0 *count(case when check_result in ('Отклонение', 'Есть изменение')  then 1 end) / count(1)), '%') as percentage
from kkd_logs_deviations kkd
where not exists  (select * from backup
										where kkd.table_name=backup.objects_name
										and kkd.date_check<=backup.date_start)
and kkd.table_name in(
    {0}
)
group by table_name, name_check
order by table_name, name_check
;

/*
 Запрос на первую проверку - Уникальность
 */
