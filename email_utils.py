import smtplib
import traceback
from functools import wraps
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class EmailNotifier:
    def __init__(self, account, password, smtp_server, smtp_port=465):
        self.account = account
        self.password = password
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port

    def send_email(self, subject, content, to_addrs=None):
        if to_addrs is None:
            to_addrs = [self.account]
        try:
            msg = MIMEMultipart()
            msg['From'] = self.account
            msg['To'] = ",".join(to_addrs)
            msg['Subject'] = subject
            msg.attach(MIMEText(content, 'plain', 'utf-8'))

            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                server.login(self.account, self.password)
                server.sendmail(self.account, to_addrs, msg.as_string())

            print("邮件发送成功")
        except Exception:
            print("邮件发送失败")
            print(traceback.format_exc())


def notify_by_email(subject_prefix="任务执行结果"):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            notifier = kwargs.pop("notifier")
            try:
                result = func(*args, **kwargs)
                subject = f"{subject_prefix} - 成功"
                content = f"函数 {func.__name__} 执行成功。\n\n结果：{result}"
                notifier.send_email(subject, content)
                return result
            except Exception as e:
                subject = f"{subject_prefix} - 失败"
                content = f"函数 {func.__name__} 执行出错：{str(e)}\n\n详情：\n{traceback.format_exc()}"
                notifier.send_email(subject, content)
                raise
        return wrapper
    return decorator
