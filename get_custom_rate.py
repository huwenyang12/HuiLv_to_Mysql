from clicknium import clicknium as cc, locator
from time import sleep
import MySQLdb
import MySQLdb.cursors as cors
import traceback
from datetime import datetime
from dateutil.relativedelta import relativedelta

import os
import logging

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs.log")
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)
logger = logging.getLogger("CustomRate")


class CustomRate():

    def get_conn(self):
        return MySQLdb.connect(
            host="123.60.179.95",
            port=3306,
            user="root",
            passwd="admin.789",
            db="ysx-cms",
            charset='utf8mb4',
            cursorclass=cors.DictCursor
        )

    def _get_next_month_range(self):
        """
        返回下个月的查询范围：start_month=end_month=YYYY-MM
        """
        next_month_dt = datetime.now() + relativedelta(months=1)
        ym = next_month_dt.strftime("%Y-%m")
        return ym, ym

    def _has_month_data(self, month_ym: str, min_count: int = 1) -> bool:
        """
        month_ym: 'YYYY-MM'
        当该月记录数 >= min_count 时，认为抓取成功 -> 直接跳过
        """
        month_int = int(month_ym.replace("-", ""))
        sql = "SELECT COUNT(*) AS cnt FROM cms_custom_rate_month WHERE month=%s"
        conn = None
        cur = None
        try:
            conn = self.get_conn()
            cur = conn.cursor()
            cur.execute(sql, (month_int,))
            row = cur.fetchone()
            cnt = int((row or {}).get("cnt", 0))
            return cnt >= int(min_count)
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def main(self, start_month=None, end_month=None):
        logger.info("任务开始")

        # 不传则默认只抓下个月
        if not start_month or not end_month:
            start_month, end_month = self._get_next_month_range()
            logger.info(f"[CustomRate] 本次仅抓取下个月汇率：{start_month} ~ {end_month}")

        # 抓取前先查库，下个月已有数据就不抓
        if start_month == end_month and self._has_month_data(start_month):
            logger.info(f"[CustomRate] {start_month} 已存在数据，跳过抓取。")
            logger.info("任务结束（跳过抓取）")
            return

        tab = None
        try:
            tab = cc.chrome.open("https://www.guanwuxiaoer.com/haiguanhuilv.php")
            logger.info("已打开网页")

            try:
                elem = tab.wait_appear(locator.guanwuxiaoer.img_close, wait_timeout=2)
                if elem:
                    elem.click()
                    logger.info("已关闭弹窗")
            except Exception:
                logger.debug("关闭弹窗失败（可忽略）")

            tab.wait_appear(locator.guanwuxiaoer.input_开始月份)

            # 开始/结束分别填
            tab.find_element(locator.guanwuxiaoer.input_开始月份).set_text(start_month)
            sleep(1)
            tab.find_element(locator.guanwuxiaoer.input_结束月份).set_text(end_month)
            sleep(1)
            tab.find_element(locator.guanwuxiaoer.input_开始月份).set_text(start_month)
            sleep(1)

            # 校验开始月份
            if tab.find_element(locator.guanwuxiaoer.input_开始月份).get_text() != start_month:
                raise Exception("查询错误，开始月份不对应")

            tab.find_element(locator.guanwuxiaoer.button_查询).click()
            sleep(5)

            if tab.wait_appear(locator.guanwuxiaoer.span_共_120_条) is None:
                raise Exception("查询超时")

            total_info = tab.find_element(locator.guanwuxiaoer.span_共_120_条).get_text()
            total = int(total_info.replace("共", "").replace("条", "").strip())
            pagecount = total // 10 if total % 10 == 0 else total // 10 + 1
            logger.info(f"查询结果 total={total}, pagecount={pagecount}")

            start_int = int(start_month.replace("-", ""))
            end_int = int(end_month.replace("-", ""))

            for page in range(pagecount):
                tab.find_element(locator.guanwuxiaoer.number_el_input_inner).set_text(page + 1)
                sleep(1)

                tab.find_element(locator.guanwuxiaoer.span_共_120_条).click()
                sleep(3)

                for rowIndex in range(10):
                    if tab.wait_appear(locator.guanwuxiaoer.币种中文, {"index": rowIndex + 1}, wait_timeout=10) is None:
                        break

                    cur_month = tab.find_element(locator.guanwuxiaoer.适用月份, {"index": rowIndex + 1}).get_text().strip()
                    cur_int = int(cur_month.replace("-", ""))

                    if cur_int < start_int or cur_int > end_int:
                        continue

                    chName = tab.find_element(locator.guanwuxiaoer.币种中文, {"index": rowIndex + 1}).get_text().strip()
                    enName = tab.find_element(locator.guanwuxiaoer.币种英文, {"index": rowIndex + 1}).get_text().strip()
                    code = tab.find_element(locator.guanwuxiaoer.币种代码, {"index": rowIndex + 1}).get_text().strip()
                    rate = tab.find_element(locator.guanwuxiaoer.海关汇率, {"index": rowIndex + 1}).get_text().strip()

                    logger.info(f"{[chName, enName, code, rate, cur_month]}")

                    self.insert_qcca_base([chName, enName, code, rate, cur_month])

            logger.info("任务结束（抓取完成）")

        except Exception as e:
            logger.error("任务异常：%s", traceback.format_exc())
            raise

        finally:
            if tab:
                try:
                    tab.close()
                    logger.info("已关闭网页")
                except Exception:
                    logger.debug("关闭网页失败（可忽略）")


    def insert_qcca_base(self, params):
        chName, enName, code, rate, month = params

        month_int = int(month.replace("-", ""))
        rate_float = float(rate)
        release_date = datetime.now()

        sql = """INSERT ignore INTO cms_custom_rate_month
                 (month, rate, currency_code, currency_name_cn, currency_name_en, release_date)
                 VALUES (%s, %s, %s, %s, %s, %s)"""

        retry_times = 3
        while True:
            if retry_times < 0:
                raise Exception("入库失败，已重试3次")

            conn = None
            cur = None
            try:
                conn = self.get_conn()
                cur = conn.cursor()

                cur.execute(sql, (month_int, rate_float, code, chName, enName, release_date))
                conn.commit()

                msg = f"成功插入数据：{chName} ({code}) - {rate_float}"
                logger.info(msg)
                break

            except Exception:
                err = "插入失败，" + traceback.format_exc()
                logger.error(err)

                if conn:
                    conn.rollback()
                retry_times -= 1

            finally:
                if cur:
                    cur.close()
                if conn:
                    conn.close()


if __name__ == "__main__":
    logger.info("========== 任务启动 ==========")
    customrate = CustomRate()
    customrate.main()
