from audit.reporting.stats import wilson, paired_flip_test
print("v1 5/10 correct:", wilson(5, 10))
print("v2 2/10 correct:", wilson(2, 10))
print("flip test if v1 fixed 1 and broke 4 -> p =", paired_flip_test(1, 4))
