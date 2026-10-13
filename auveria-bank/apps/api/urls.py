from django.urls import path

from . import views

urlpatterns = [
    path("auth/register/", views.RegisterView.as_view()),
    path("auth/login/", views.LoginView.as_view()),
    path("whoami/", views.WhoAmIView.as_view()),
    path("me/", views.MeView.as_view()),
    path("pin/", views.SetPinView.as_view()),
    path("otp/request/", views.OtpRequestView.as_view()),
    path("accounts/", views.AccountListView.as_view()),
    path("accounts/lookup/<str:account_number>/", views.AccountLookupView.as_view()),
    path("accounts/<str:account_number>/transactions/", views.StatementView.as_view()),
    path("transfers/", views.TransferView.as_view()),
    path("staff/accounts/<str:account_number>/", views.StaffAccountView.as_view()),
    path("staff/cash-journal/", views.StaffCashJournalView.as_view()),
    path("staff/deposits/", views.StaffDepositView.as_view()),
    path("staff/withdrawals/", views.StaffWithdrawalView.as_view()),
]
