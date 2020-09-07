#include <iostream>

#define N ((1<<64) -1)

using namespace std;

int main() {
    volatile uint64_t sum = 0;

    for (uint64_t i = 0; i < N; i++) {
        sum += i;
    }

    std::cout << "sum = " << sum << std::endl;

    return 0;
}
